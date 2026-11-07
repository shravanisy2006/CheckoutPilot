// Inkwell & Co. - checkout page using the LEGACY PayPal JS SDK v5 (paypal.Buttons).
// The server works out the price; the browser only sends item IDs and quantities.

const statusBox = document.getElementById("order-status");

function showStatus(message, kind) {
  statusBox.textContent = message;
  statusBox.className = kind || "";
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || ("Request failed (" + response.status + ")"));
  }
  return data;
}

async function setUpCheckout() {
  const total = await renderCartLines(document.getElementById("cart-lines"));
  document.getElementById("cart-total").textContent = "$" + total.toFixed(2);
  const cart = readCart();
  if (cart.length === 0) {
    document.getElementById("cart-empty").hidden = false;
    return;
  }

  if (typeof paypal === "undefined") {
    showStatus("PayPal could not load. Check your internet connection or PAYPAL_CLIENT_ID.", "error");
    return;
  }

  paypal.Buttons({
    style: { layout: "vertical", label: "paypal" },

    createOrder: async function () {
      showStatus("Creating your PayPal order...");
      const order = await postJson("/api/orders", { items: readCart() });
      return order.id;
    },

    onApprove: async function (data) {
      showStatus("Capturing payment...");
      const result = await postJson("/api/orders/" + encodeURIComponent(data.orderID) + "/capture");
      clearCart();
      window.location.href = "/success?order=" + encodeURIComponent(result.id);
    },

    onCancel: function () {
      showStatus("Payment cancelled. Your cart is still saved.");
    },

    onError: function (error) {
      showStatus("Payment failed: " + (error && error.message ? error.message : error), "error");
    },
  }).render("#paypal-button-container");
}

setUpCheckout().catch((error) => showStatus("Could not load checkout: " + error.message, "error"));
