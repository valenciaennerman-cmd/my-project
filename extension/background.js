chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "fetch_api") {
        fetch(request.url, {
            method: request.method || 'GET',
            headers: request.headers || {},
            body: request.body ? JSON.stringify(request.body) : null
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw err; }).catch(() => { throw new Error("API Error"); });
            }
            return response.json();
        })
        .then(data => {
            sendResponse({ success: true, data: data });
        })
        .catch(error => {
            console.error("Background Fetch Error:", error);
            sendResponse({ success: false, error: error.message || error.detail || "Bağlantı hatası" });
        });

        return true; // Asenkron yanit verilecegini belirtir
    }
});
