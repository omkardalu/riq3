/* Resume IQ shared navigation + footer for public content pages. Needs riq.js. */
(function () {
  "use strict";

  var NAV = [
    ["Home", "homepage.html"],
    ["Features", "features.html"],
    ["How It Works", "how-it-works.html"]
  ];
  var FOOT = NAV.concat([["Upload Resumes", "upload.html"], ["Results", "ats-score.html"], ["Profile", "profile.html"]]);

  function current() { return location.pathname.split("/").pop(); }

  function link(href, label, active) {
    return '<a href="' + href + '"' + (active ? ' class="active" aria-current="page"' : "") + ">" + label + "</a>";
  }

  function navHTML() {
    var here = current();
    return '<header class="site-nav">' +
      '<a class="site-logo" href="homepage.html">RESUME <span>IQ</span></a>' +
      '<nav class="site-links" aria-label="Main">' + NAV.map(function (n) { return link(n[1], n[0], n[1] === here); }).join("") + "</nav>" +
      '<div class="site-account" id="siteAccount"></div></header>';
  }

  function footerHTML() {
    return '<footer class="site-footer"><div class="site-footer-logo">RESUME <span>IQ</span></div>' +
      "<p>Rule-based resume screening.</p>" +
      '<nav class="site-footer-links" aria-label="Footer">' + FOOT.map(function (n) { return link(n[1], n[0], false); }).join("") + "</nav>" +
      "<p>DEVELOPED BY Jaswanth And Team</p>" +
      '<p class="copyright">&copy; 2026 Resume IQ. All rights reserved.</p></footer>';
  }

  function account() {
    var box = document.getElementById("siteAccount");
    return RIQ.api("/api/auth/me", { redirectOn401: false }).then(function () {
      box.innerHTML = '<button type="button" class="site-menu-btn" id="menuButton" aria-label="Account menu"><span></span><span></span><span></span></button>' +
        '<div class="dropdown" id="dropdown"><button type="button" id="profileButton">Profile</button><button type="button" id="logoutButton">Logout</button></div>';
      RIQ.initMenu();
    }).catch(function () {
      box.innerHTML = '<a href="login.html">Login</a><a href="create-account.html">Create account</a>';
    });
  }

  document.body.insertAdjacentHTML("afterbegin", navHTML());
  document.body.insertAdjacentHTML("beforeend", footerHTML());
  account();
})();
