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

// Don't upload data to mozilla
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("privacy.donottrackheader.enabled", true);

// Disable password storage
user_pref("signon.rememberSignons", false);

// Hide some buttons
user_pref("browser.uiCustomization.state", "{\"placements\":{\"widget-overflow-fixed-list\":[],\"PersonalToolbar\":[\"personal-bookmarks\"],\"nav-bar\":[\"back-button\",\"forward-button\",\"stop-reload-button\",\"customizableui-special-spring1\",\"urlbar-container\",\"customizableui-special-spring2\",\"downloads-button\",\"ublock0-button\",\"screenshots_mozilla_org-browser-action\"],\"TabsToolbar\":[\"tabbrowser-tabs\",\"new-tab-button\",\"alltabs-button\"],\"toolbar-menubar\":[\"menubar-items\"],\"addon-bar\":[\"addonbar-closebutton\",\"status-bar\"],\"dactyl-addon-bar\":[\"dactyl-status-bar\"]},\"seen\":[\"pocket-button\",\"ublock0-button\",\"developer-button\",\"webide-button\",\"ublock0_raymondhill_net-browser-action\",\"screenshots_mozilla_org-browser-action\"],\"dirtyAreaCache\":[\"PersonalToolbar\",\"nav-bar\",\"TabsToolbar\",\"toolbar-menubar\",\"dactyl-addon-bar\",\"PanelUI-contents\",\"addon-bar\"],\"currentVersion\":12,\"newElementCount\":2}");

// Dark theme
user_pref("lightweightThemes.persisted.footerURL", false);
user_pref("lightweightThemes.persisted.headerURL", false);
user_pref("lightweightThemes.selectedThemeID", "firefox-compact-dark@mozilla.org");
