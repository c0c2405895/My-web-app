const $ = (id) => document.getElementById(id);

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

function openModal() {
  $("modal").classList.remove("hidden");
}

function closeModal() {
  $("modal").classList.add("hidden");
  $("formError").textContent = "";
}

async function loadWardrobe() {
  const response = await fetch("/api/dashboard");
  if (!response.ok) throw new Error("データを読み込めませんでした");
  const { items } = await response.json();
  $("itemCount").textContent = `${items.length} ITEMS`;
  const groups = { outer: [], bottom: [] };
  items.forEach((item) => {
    if (item.category === "ボトムス") groups.bottom.push(item);
    else groups.outer.push(item);
  });
  renderGroup("outer", groups.outer);
  renderGroup("bottom", groups.bottom);
}

function renderGroup(name, items) {
  $(`${name}Count`).textContent = `${items.length} ITEMS`;
  $(`${name}Grid`).innerHTML = items.length
    ? items.map((item) => `
      <article class="wardrobe-item"><div class="wardrobe-image">${item.image ? `<img src="${item.image}" alt="${item.name}">` : "◌"}</div>
        <div class="wardrobe-info"><b>${item.name}</b><small>${item.category}　·　${item.material || "混紡"}</small></div></article>`).join("")
    : '<p class="empty-category">登録されていません</p>';
}

$("itemForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formError = $("formError");
  formError.textContent = "";
  const response = await fetch("/api/items", { method: "POST", body: new FormData(event.target) });
  if (!response.ok) {
    formError.textContent = (await response.json()).error || "登録に失敗しました";
    return;
  }
  event.target.reset();
  closeModal();
  await loadWardrobe();
  showToast("ワードローブに登録しました");
});

loadWardrobe().catch(() => showToast("データの読み込みに失敗しました"));
