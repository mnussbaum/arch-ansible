// High DPI
user_pref("layout.css.devPixelsPerPx", "2");

// Hardware accelerate with OpenGL
user_pref("layers.acceleration.force-enabled", true);

// Enable pipelining
user_pref("network.http.pipelining", true);
user_pref("network.http.pipelining.ssl", true);
user_pref("network.http.proxy.pipelining", true);

// Enable HTTP cache
user_pref("browser.cache.use_new_backend", 1);

// Make pages render immediately
user_pref("nglayout.initialpaint.delay", 0);

// Decrease disk writes, less frequent session restore writes
user_pref("browser.sessionstore.interval", 300000);

// Restore session at startup
user_pref("browser.startup.page", 3);
