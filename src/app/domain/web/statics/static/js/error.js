document.body.addEventListener("htmx:afterRequest", function (evt) {
  const networkErrorElem = document.getElementById("htmx-error-alert");
  const apiErrorElem = document.querySelector("span.error");
  if (evt.detail.successful) {
    // Success, clear error alert
    networkErrorElem.setAttribute("hidden", "true");
    networkErrorElem.removeAttribute("class");
    networkErrorElem.innerText = "";
    if (apiErrorElem && evt.detail.xhr.status < 400) {
      apiErrorElem.remove();
    }
  } else if (evt.detail.failed && evt.detail.xhr) {
    // Server error with a response, equivalent to htmx:responseError
    console.warn("Server error", evt.detail);
    const xhr = evt.detail.xhr;
    networkErrorElem.innerText = `Unexpected server error: ${xhr.status} - ${xhr.statusText}`;
    networkErrorElem.removeAttribute("hidden");
    networkErrorElem.setAttribute("class", "error");
  } else {
    // Usually a network error
    console.error("Unexpected error.", evt.detail);
    networkErrorElem.innerText = "Network error, try again later.";
    networkErrorElem.removeAttribute("hidden");
    networkErrorElem.setAttribute("class", "error");
  }
});

document.body.addEventListener("cleanErrors", function (evt) {
  // removes the span element so it doesn't stack
  const apiErrorElem = document.querySelector("span.error");
  if (apiErrorElem) {
    apiErrorElem.remove();
  }
});
