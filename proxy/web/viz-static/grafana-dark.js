'use strict'

// Grafana Dark Theme
// Clear IndexedDB to prevent auth hangup in the proxied Powerwall web app.
try {
    window.indexedDB.databases().then((dbs) => {
        dbs.forEach(db => { window.indexedDB.deleteDatabase(db.name) });
    });
} catch (error) {
    document.write("Browser blocking indexedDB - Turn off incognito mode.");
}

function injectScriptAndUse() {
    return new Promise((resolve, reject) => {
        var body = document.getElementsByTagName("body")[0];
        var script = document.createElement("script");
        script.src = "//ajax.googleapis.com/ajax/libs/jquery/1.11.1/jquery.min.js";
        script.onload = function () {
            resolve();
        };
        body.appendChild(script);
    });
}

injectScriptAndUse().then(() => {
    console.log("Applying Grafana customization");
    triggerOnMutation(formatPowerwallForGrafana);
});

function triggerOnMutation(cb) {
    // Create an observer instance
    var observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            var newNodes = mutation.addedNodes; // DOM NodeList
            if (newNodes !== null) { // If there are new nodes added
                if (cb) cb();
            }
        });
    });

    // Configuration of the observer:
    var config = {
        attributes: true,
        childList: true,
        subtree: true,
    };

    var target = $("#root")[0];

    // Pass in the target node, as well as the observer options
    observer.observe(target, config);
}

function formatPowerwallForGrafana() {
    // Hide elements.
    $('.overview-menu, #logout, .footer, .compact-btn-row, .toast-list, .power-flow-header, .btn').hide();

    // Set alignment
    $('.core-layout__viewport').css({
        padding: 0,
        margin: 0,
    });

    $('.power-flow-header').css({
        "padding-top": 0,
    });

    $('.power-flow-grid').css({
        width: "100%",
        left: 0,
        right: 0,
        margin: 0,
        "padding-top": 0,
        "position": "fixed",
    });

    $('.app').css({
        "overflow-y": "hidden",
    });

    // Set colors
    $('body').css({
        "background-color": "#111217",
    });

    $('.power-flow-grid.active').css({
        "background-color": "#111217",
    });
}