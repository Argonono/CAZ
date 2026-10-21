// CareAtZero service worker.
// Saves the launcher page and icons on the phone so the app opens instantly
// and can show the offline screen (with 911 / 988) when there's no signal.
// Clinic data is NOT cached: it always comes live from the Streamlit app.
// Change CACHE whenever these files change, so phones pick up the new version.

const CACHE = "careatzero-shell-v1";
const SHELL = [
  "./",
  "index.html",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/icon-maskable-512.png",
  "icons/apple-touch-icon.png",
  "icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Remove older versions of the saved files
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return; // leave the Streamlit app alone

  if (event.request.mode === "navigate") {
    // Opening the app: try the network first, fall back to the saved page
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put("index.html", copy));
          return res;
        })
        .catch(() => caches.match("index.html"))
    );
    return;
  }

  // Icons and the manifest: use the saved copy when there is one
  event.respondWith(caches.match(event.request).then((hit) => hit || fetch(event.request)));
});
