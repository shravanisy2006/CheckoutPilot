// Inkwell & Co. - catalogue pages: quick "Add to cart" buttons and the cart count.
function updateCartCount() {
  const count = readCart().reduce((sum, item) => sum + item.qty, 0);
  const el = document.getElementById("cart-count");
  if (el) el.textContent = String(count);
}

function showNotice(text) {
  const el = document.getElementById("cart-notice");
  if (el) el.textContent = text;
}

document.querySelectorAll(".quick-add").forEach((button) => {
  button.addEventListener("click", () => {
    addToCart(button.dataset.id, 1);
    updateCartCount();
    button.textContent = "Added";
    showNotice("Added to your cart.");
  });
});

// Product detail pages (/product/<id>): the main Add to cart button.
const mainAdd = document.getElementById("add-to-cart");
if (mainAdd && mainAdd.dataset.id) {
  mainAdd.addEventListener("click", () => {
    const qty = Math.max(1, Math.min(10, parseInt(document.getElementById("qty").value, 10) || 1));
    addToCart(mainAdd.dataset.id, qty);
    updateCartCount();
    showNotice("Added to your cart.");
  });
}

updateCartCount();
