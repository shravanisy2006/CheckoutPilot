// Inkwell & Co. - shared cart helpers (cart lives in the browser's localStorage).
const CART_KEY = "inkwell_cart";

function readCart() {
  try {
    const items = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    return Array.isArray(items) ? items : [];
  } catch (error) {
    return [];
  }
}

function writeCart(items) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(items));
  } catch (error) {
    /* storage unavailable: cart works for this page only */
  }
}

function addToCart(id, qty) {
  const items = readCart();
  const existing = items.find((item) => item.id === id);
  if (existing) {
    existing.qty = Math.min(existing.qty + qty, 10);
  } else {
    items.push({ id: id, qty: qty });
  }
  writeCart(items);
  return items;
}

function clearCart() {
  writeCart([]);
}

async function loadProducts() {
  const response = await fetch("/api/products");
  const data = await response.json();
  const byId = {};
  data.products.forEach((product) => { byId[product.id] = product; });
  return { currency: data.currency, byId: byId };
}

// Fill a <tbody> with cart lines and return the total (as a number).
async function renderCartLines(tbody) {
  const cart = readCart();
  const catalogue = await loadProducts();
  let total = 0;
  tbody.innerHTML = "";
  cart.forEach((item) => {
    const product = catalogue.byId[item.id];
    if (!product) return;
    const lineTotal = Number(product.price) * item.qty;
    total += lineTotal;
    const row = document.createElement("tr");
    row.innerHTML =
      "<td></td><td class=\"num\"></td><td class=\"num\"></td>";
    row.children[0].textContent = product.name;
    row.children[1].textContent = String(item.qty);
    row.children[2].textContent = "$" + lineTotal.toFixed(2);
    tbody.appendChild(row);
  });
  return total;
}
