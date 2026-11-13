const notificationStorageKey = "ai-wardrobe-last-notification";
const notificationLockKey = "ai-wardrobe-notification-lock";

function showPageNotification(message = "今日のおすすめの洋服を選びました！") {
  let banner = document.getElementById("pageNotification");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "pageNotification";
    banner.className = "page-notification";
    document.body.appendChild(banner);
  }
  banner.innerHTML = `${message} <a href="/#outfit-recommendation">今日のおすすめを見る</a>`;
  banner.classList.add("show");
  window.setTimeout(() => banner.classList.remove("show"), 5000);
}

function notificationDateKey() {
  return new Intl.DateTimeFormat("sv-SE").format(new Date());
}

async function requestNotificationPermission() {
  if (!window.isSecureContext || !("Notification" in window)) return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  return (await Notification.requestPermission()) === "granted";
}

async function showOutfitNotification(force = false) {
  if (!window.isSecureContext || !("Notification" in window) || Notification.permission !== "granted") return false;
  const dateKey = notificationDateKey();
  if (!force) {
    const lock = JSON.parse(localStorage.getItem(notificationLockKey) || "null");
    if (localStorage.getItem(notificationStorageKey) === dateKey) return true;
    if (lock && lock.date === dateKey && Date.now() - lock.timestamp < 30000) return true;
    localStorage.setItem(notificationLockKey, JSON.stringify({date: dateKey, timestamp: Date.now()}));
    if (localStorage.getItem(notificationStorageKey) === dateKey) return true;
    localStorage.setItem(notificationStorageKey, dateKey);
  }
  showPageNotification();
  try {
    const registration = await navigator.serviceWorker.ready;
    await registration.showNotification("今日のコーディネート", {
      body: "今日のおすすめコーデを確認しましょう。",
      tag: "ai-wardrobe-outfit",
      renotify: true,
    });
  } catch {
    try {
      new Notification("今日のコーディネート", {
        body: "今日のおすすめコーデを確認しましょう。",
      });
    } catch {
      return false;
    }
  }
  return true;
}

async function checkNotificationSchedule() {
  const response = await fetch("/api/dashboard");
  if (!response.ok) return;
  const { settings } = await response.json();
  if (!settings.notifications) return;
  const [hours, minutes] = String(settings.notification_time).split(":").map(Number);
  if (!Number.isInteger(hours) || !Number.isInteger(minutes)) return;
  const now = new Date();
  const scheduledAt = new Date(now);
  scheduledAt.setHours(hours, minutes, 0, 0);
  if (now >= scheduledAt) await showOutfitNotification();
}

window.enableOutfitNotifications = requestNotificationPermission;
window.showTestOutfitNotification = async () => {
  if (!window.isSecureContext) {
    showPageNotification("アプリ内通知：今日のおすすめを確認しましょう");
    return {
      sent: true,
      message: "アプリ内通知を表示しました（スマホのシステム通知はHTTPSが必要です）"
    };
  }
  if (!("Notification" in window)) return { sent: false, message: "このブラウザーは通知に対応していません" };
  const permissionGranted = await requestNotificationPermission();
  if (!permissionGranted) return { sent: false, message: `通知が許可されていません（${Notification.permission}）` };
  const sent = await showOutfitNotification(true);
  return { sent, message: sent ? "テスト通知を送りました" : "通知の表示に失敗しました" };
};
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/notifications-sw.js").catch(() => {});
}
setInterval(() => checkNotificationSchedule().catch(() => {}), 15000);
checkNotificationSchedule().catch(() => {});
