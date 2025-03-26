'use strict'

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
    console.log("Applying SolarOnly customization");
    triggerOnMutation(formatPowerwallForSolar);
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

function formatPowerwallForSolar() {
    // Hide elements.
    $('.overview-menu, #logout, .footer, .compact-btn-row, .toast-list, .power-flow-header, .btn, .powerwall-soe, .soe-label').hide();

    // Hide Powerwall image 
    var imgElement = document.querySelector('[data-testid="b3372156-8a9e-4d17-9721-fcc5891d1074"]');
    if (imgElement) {
        imgElement.style.display = 'none';
    }
    // Hide the Powerwall text
    const divs = document.querySelectorAll('[data-testid="ec7d6a6d-b6d2-411c-a535-c052c00baf62"]');
    divs.forEach(div => {
        if (div.style.width === '120px' && div.style.top === '200.5px' && div.style.left === '0px' && div.style.right === '0px') {
            const paragraph = div.querySelector('p[data-testid="4c6aadb3-7661-4d7f-b1ff-d5a0571fac60"]');
            if (paragraph) {
                paragraph.style.display = 'none';
            }
        }
    });

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
        "background-color": "transparent",
    });

    $('.power-flow-grid.active').css({
        "background-color": "transparent",
    });
}
