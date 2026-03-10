function getSessionId() {
    let sessionId = localStorage.getItem("sessionId");
    if (!sessionId) {
        sessionId = "session-" + Date.now();
        localStorage.setItem("sessionId", sessionId);
    }
    return sessionId;
}

function addMessage(text, className) {
    const messagesDiv = document.getElementById("messages");
    const msg = document.createElement("div");
    msg.className = className;
    msg.textContent = text;
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

document.getElementById("send-button").addEventListener("click", sendMessage);

async function sendMessage() {
    const input = document.getElementById("user-input");
    const messageText = input.value.trim();

    if (!messageText) return;

    addMessage(messageText, "user-message");
    input.value = "";

    addMessage("Loading...", "assistant-message");

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                sessionId: getSessionId(),
                message: messageText
            })
        });

        const data = await response.json();

        const messagesDiv = document.getElementById("messages");
        messagesDiv.removeChild(messagesDiv.lastChild);

        if (data.error) {
            addMessage("Error: " + data.error, "assistant-message");
        } else {
            addMessage(data.reply, "assistant-message");
        }
    } catch (error) {
        const messagesDiv = document.getElementById("messages");
        messagesDiv.removeChild(messagesDiv.lastChild);
        addMessage("Error: Could not connect to server.", "assistant-message");
    }
}