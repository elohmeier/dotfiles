"use strict";
history.replaceState(null, "", "/egress");
const requests = document.querySelector("#requests");
const error = document.querySelector("#error");
const choices = [
  ["allow", "Allow once"], ["allow-session", "Allow session"], ["allow-always", "Always allow"],
  ["deny", "Deny once"], ["deny-session", "Deny session"], ["deny-always", "Always deny"],
];
async function refresh() {
  try {
    const response = await fetch("/egress/pending");
    if (!response.ok) throw new Error("Connection lost. Reopen mise run pi:egress web to reconnect.");
    const state = await response.json();
    document.querySelector("#status").textContent = `Mode: ${state.mode} · Recording: ${state.record ? "on" : "off"}`;
    document.querySelector("#empty").hidden = state.requests.length !== 0;
    const ids = new Set(state.requests.map(request => request.id));
    for (const article of requests.children) if (!ids.has(article.id)) article.remove();
    for (const request of state.requests) {
      let article = document.getElementById(request.id);
      if (!article) {
        article = document.createElement("article");
        article.id = request.id;
        const title = document.createElement("h2");
        title.textContent = request.target;
        article.append(title, document.createElement("p"));
        for (const [choice, label] of choices) {
          const button = document.createElement("button");
          button.textContent = label;
          button.onclick = async () => {
            for (const sibling of article.querySelectorAll("button")) sibling.disabled = true;
            try {
              const result = await fetch(`/egress/decision/${request.id}`, {
                method: "POST",
                headers: {"Content-Type": "application/json", "X-XSRFToken": document.body.dataset.xsrf},
                body: JSON.stringify({choice}),
              });
              if (!result.ok) throw new Error(await result.text());
              error.textContent = "";
            } catch (failure) {
              error.textContent = failure.message;
              for (const sibling of article.querySelectorAll("button")) sibling.disabled = false;
            }
          };
          article.append(button);
        }
        requests.append(article);
      }
      article.querySelector("p").textContent = `Denied automatically in ${Math.max(0, Math.ceil(request.expires - Date.now() / 1000))}s`;
    }
  } catch (failure) { error.textContent = failure.message; }
  setTimeout(refresh, 750);
}
refresh();
