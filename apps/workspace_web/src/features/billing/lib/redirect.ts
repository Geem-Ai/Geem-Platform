/** Navigate the browser to a hosted checkout page. Gateway-neutral. */
export function redirectToCheckout(url: string): void {
  window.location.assign(url);
}
