let state = { outfit: { items: [] } };

const $ = (id) => document.getElementById(id);
function renderTodayDate() {
  $("todayDate").textContent = new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date()).toUpperCase();
}
function scrollToId(id) { $(id).scrollIntoView({ behavior: "smooth" }); }
function showToast(message) { const toast = $("toast"); toast.textContent = message; toast.classList.add("show"); setTimeout(() => toast.classList.remove("show"), 2600); }
function openModal() { $("modal").classList.remove("hidden"); }
function closeModal() { $("modal").classList.add("hidden"); $("formError").textContent = ""; }

async function loadDashboard() {
  const response = await fetch(`/api/dashboard?refresh=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error("データを読み込めませんでした");
  state = await response.json();
  render();
}

function render() {
  const { weather, outfit, items, settings } = state;
  renderTodayDate();
  $("weatherLocation").textContent = weather.location;
  $("temperature").textContent = `${weather.temperature}°`;
  $("feelsLike").textContent = weather.feels_like;
  $("condition").textContent = weather.condition;
  $("weatherIcon").textContent = weather.rain ? "☂" : weather.condition === "くもり" ? "☁" : "☀";
  $("rainChance").textContent = weather.rain ? "60%" : "10%";
  $("temperatureRange").textContent = Number.isFinite(weather.temperature_max) && Number.isFinite(weather.temperature_min)
    ? `${weather.temperature_max}° / ${weather.temperature_min}°`
    : "--";
  $("notificationTime").textContent = settings.notification_time;
  $("notificationToggle").checked = settings.notifications;
  $("outfitItems").innerHTML = outfit.items.length ? outfit.items.map((item) => `
    <div class="outfit-item">${item.image ? `<img src="${item.image}" alt="${item.name}">` : '<div class="outfit-placeholder">◌</div>'}
      <div class="item-caption">${item.name}<small>${item.category} / ${item.material || "混紡"}</small></div>
    </div>`).join("") : '<div class="outfit-placeholder">まずは服を登録しましょう</div>';
  const missingMessage = outfit.missing?.length
    ? `<li class="missing-note">手持ちに${outfit.missing.join("・")}がありません</li>` : "";
  const suggestions = (outfit.purchase_suggestions || []).map((item) => `
    <div class="purchase-suggestion"><b>購入候補：${item.name}</b><small>${item.reason}</small></div>`).join("");
  $("reasons").innerHTML = missingMessage + outfit.reasons.map((reason) => `<li>${reason}</li>`).join("") + suggestions;
  renderFeedbackState();
}

function renderFeedbackState(selectedValue = null) {
  const latestFeedback = new Map();
  for (const entry of state.feedback || []) {
    latestFeedback.set(entry.item_id, entry.value);
  }
  const values = selectedValue
    ? [selectedValue]
    : (state.outfit.items || []).map((item) => latestFeedback.get(item.id)).filter(Boolean);
  const value = selectedValue || (values.length && values.every((entry) => entry === values[0]) ? values[0] : null);
  const likeButton = $("likeButton");
  const dislikeButton = $("dislikeButton");
  likeButton.classList.toggle("selected-like", value === "like");
  dislikeButton.classList.toggle("selected-dislike", value === "dislike");
  likeButton.setAttribute("aria-pressed", String(value === "like"));
  dislikeButton.setAttribute("aria-pressed", String(value === "dislike"));
}

async function refreshOutfit() {
  await loadDashboard();
  showToast("新しいコーデを提案しました");
}

async function sendOverallFeedback(value) {
  const items = state.outfit.items;
  renderFeedbackState(value);
  await Promise.all(items.map((item) => fetch("/api/feedback", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_id: item.id, value })
  })));
  showToast(value === "like" ? "好みを学習しました" : "次回の提案に反映します");
  await loadDashboard();
}

async function saveSettings() {
  await fetch("/api/settings", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notifications: $("notificationToggle").checked })
  });
  showToast($("notificationToggle").checked ? "毎朝の通知をオンにしました" : "毎朝の通知をオフにしました");
}

$("itemForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formError = $("formError");
  formError.textContent = "";
  const response = await fetch("/api/items", { method: "POST", body: new FormData(event.target) });
  if (!response.ok) { formError.textContent = (await response.json()).error || "登録に失敗しました"; return; }
  event.target.reset(); closeModal(); await loadDashboard(); showToast("ワードローブに登録しました");
});

loadDashboard().catch(() => showToast("データの読み込みに失敗しました"));
