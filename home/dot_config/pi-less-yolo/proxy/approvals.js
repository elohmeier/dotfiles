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
    document.querySelector("#status").textContent = `Project: ${state.project} · Mode: ${state.mode} · Recording: ${state.record ? "on" : "off"} · Save to: ${state.save_scope === "project" ? `${state.project}/mise.toml` : "global user rules"}`;
    if (state.save_error) error.textContent = state.save_error;
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
          button.dataset.choice = choice;
          button.textContent = label;
          button.onclick = async () => {
            for (const sibling of article.querySelectorAll("button")) sibling.disabled = true;
            try {
              const result = await fetch(`/egress/decision/${request.id}`, {
                method: "POST",
                headers: {"Content-Type": "application/json", "X-XSRFToken": document.body.dataset.xsrf},
                body: JSON.stringify({choice, scope: article.dataset.scope}),
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
      article.dataset.scope = state.save_scope;
      for (const button of article.querySelectorAll("button")) {
        button.disabled = request.saving;
        if (button.dataset.choice.endsWith("-always")) {
          button.textContent = `Save ${state.save_scope} ${button.dataset.choice.split("-")[0]}`;
          button.disabled = request.saving || !state.can_save;
          button.title = state.can_save ? "" : "Run mise run pi:egress web to enable saving";
        }
      }
      article.querySelector("p").textContent = `${request.saving ? "Saving through host… · " : ""}Denied automatically in ${Math.max(0, Math.ceil(request.expires - Date.now() / 1000))}s`;
    }
  } catch (failure) { error.textContent = failure.message; }
  setTimeout(refresh, 750);
}
refresh();
