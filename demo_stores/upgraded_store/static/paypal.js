// Inkwell & Co. (upgraded) - PayPal JavaScript SDK v6 one-time payment.
// Used on the cart page (express checkout) and the checkout page.
// The server works out the price; the browser only sends item IDs and quantities.

function showStatus(message, kind) {
  const box = document.getElementById("order-status");
  if (!box) return;
  box.textContent = message;
  box.className = kind || "";
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

// v6 needs a browser-safe client token from our server (the secret stays on the server).
// If that fails, fall back to the public client ID.
async function getSdkAuth() {
  try {
    const response = await fetch("/api/paypal/client-token");
    if (response.ok) {
      const data = await response.json();
      if (data.accessToken) return { clientToken: data.accessToken };
    }
  } catch (error) { /* fall through */ }
  const meta = document.querySelector('meta[name="paypal-client-id"]');
  return { clientId: meta ? meta.content : "" };
}

// The SDK wants a Promise that resolves to { orderId }.
async function createOrder() {
  const order = await postJson("/api/orders", { items: readCart() });
  return { orderId: order.id };
}

async function captureAndFinish(orderId) {
  showStatus("Capturing payment...");
  const result = await postJson("/api/orders/" + encodeURIComponent(orderId) + "/capture");
  if (result.status !== "COMPLETED") {
    showStatus("Payment not completed (status: " + result.status + "). Please try again.", "error");
    return;
  }
  clearCart();
  window.location.href = "/success?order=" + encodeURIComponent(result.id);
}

async function setUpPayPal() {
  if (readCart().length === 0) return;  // nothing to pay for
  const sdkInstance = await window.paypal.createInstance({
    ...(await getSdkAuth()),
    components: ["paypal-payments"],
    pageType: "checkout",
  });

  const methods = await sdkInstance.findEligibleMethods({ currencyCode: "USD" });
  if (!methods.isEligible("paypal")) {
    showStatus("PayPal is not available for this purchase.", "error");
    return;
  }

  const session = sdkInstance.createPayPalOneTimePaymentSession({
    onApprove: async function (data) {
      try {
        await captureAndFinish(data.orderId);
      } catch (error) {
        showStatus("Payment failed: " + error.message, "error");
      }
    },
    onCancel: function () {
      showStatus("Payment cancelled. Your cart is still saved.");
    },
    onError: function (error) {
      showStatus("Payment failed: " + (error && error.message ? error.message : error), "error");
    },
  });

  const button = document.querySelector("#paypal-button-container paypal-button");
  button.removeAttribute("hidden");
  button.addEventListener("click", async function () {
    showStatus("");
    try {
      await session.start({ presentationMode: "auto" }, createOrder());
    } catch (error) {
      showStatus("Payment failed: " + error.message, "error");
    }
  });
}

// Called by the SDK <script> tag's onload / onerror.
function onPayPalWebSdkLoaded() {
  setUpPayPal().catch((error) => showStatus("PayPal could not start: " + error.message, "error"));
}

function onPayPalWebSdkFailed() {
  showStatus("PayPal could not load. Check your internet connection.", "error");
}
