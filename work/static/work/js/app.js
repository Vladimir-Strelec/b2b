// Лёгкий параллакс: фон смещается медленнее прокрутки.
(function () {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var bg = document.querySelector(".bg");
  if (!bg) return;
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      bg.style.transform = "translate3d(0," + (-window.scrollY * 0.12) + "px,0)";
      ticking = false;
    });
  }, { passive: true });
})();

// Описание под каждым фото растёт по мере ввода текста.
(function () {
  document.querySelectorAll(".photo-description-input").forEach(function (field) {
    var resize = function () {
      field.style.height = "auto";
      field.style.height = Math.max(54, field.scrollHeight) + "px";
    };
    field.addEventListener("input", resize);
    resize();
  });
})();

// Update open-shift warning badges while the dashboard remains open.
(function () {
  var badges = document.querySelectorAll("[data-shift-start]");
  if (!badges.length) return;
  function updateShiftWarnings() {
    var now = Date.now();
    badges.forEach(function (badge) {
      var startedAt = Date.parse(badge.dataset.shiftStart);
      if (!Number.isFinite(startedAt)) return;
      var overdue = now - startedAt >= 8 * 60 * 60 * 1000;
      badge.classList.toggle("status-revision", overdue);
      badge.classList.toggle("status-approved", !overdue);
      badge.textContent = overdue ? badge.dataset.overdue : badge.dataset.onTime;
    });
  }
  updateShiftWarnings();
  window.setInterval(updateShiftWarnings, 30000);
})();

(function () {
  document.querySelectorAll(".photo-file-input").forEach(function (field) {
    field.addEventListener("change", function () {
      var area = field.parentElement;
      var label = area.querySelector(".photo-upload-control");
      var filename = area.querySelector(".photo-upload-filename");
      if (!label || !filename) return;
      if (field.files && field.files.length) {
        filename.textContent = field.files[0].name;
        label.classList.add("has-file");
      } else {
        filename.textContent = "Нажмите, чтобы выбрать файл";
        label.classList.remove("has-file");
      }
    });
  });
})();

// Live object lookup by number and address, with matching object suggestions.
(function () {
  var form = document.getElementById("site-filter-form");
  var results = document.getElementById("site-results");
  if (!form || !results) return;

  var numberInput = form.querySelector('[name="object_number"]');
  var nameInput = form.querySelector('[name="name"]');
  var addressInput = form.querySelector('[name="address"]');
  if (!numberInput || !nameInput || !addressInput) return;

  function makeSuggestions(input) {
    var panel = document.createElement("div");
    panel.className = "site-suggestions";
    panel.hidden = true;
    input.parentElement.classList.add("site-search-field");
    input.parentElement.appendChild(panel);
    return panel;
  }

  var numberPanel = makeSuggestions(numberInput);
  var addressPanel = makeSuggestions(addressInput);
  var activeInput = null;
  var debounceTimer = null;
  var requestController = null;

  function paramsFromForm() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (String(value).trim()) params.set(key, value);
    });
    return params;
  }

  function hideSuggestions() {
    numberPanel.hidden = true;
    addressPanel.hidden = true;
  }

  function fillSuggestions(panel, input, rows, attr) {
    panel.replaceChildren();
    var seen = new Set();
    rows.forEach(function (row) {
      var cell = row.querySelector("[data-object-number]");
      var addressCell = row.querySelector("[data-address]");
      if (!cell || !addressCell) return;
      var value = attr === "data-object-number" ? cell.dataset.objectNumber : addressCell.dataset.address;
      if (!value || seen.has(value)) return;
      seen.add(value);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "site-suggestion";
      button.textContent = value;
      var detail = document.createElement("small");
      detail.textContent = (row.cells[1] ? row.cells[1].innerText.split("\n")[0] : "") + " · " + addressCell.dataset.address;
      button.appendChild(detail);
      button.addEventListener("click", function () {
        input.value = value;
        activeInput = input;
        hideSuggestions();
        refreshResults(true);
        input.focus();
      });
      panel.appendChild(button);
    });
    panel.hidden = panel.childElementCount === 0;
  }

  function refreshResults(showSuggestions) {
    var params = paramsFromForm();
    var url = window.location.pathname + (params.toString() ? "?" + params.toString() : "");
    if (requestController) requestController.abort();
    requestController = new AbortController();
    fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}, signal: requestController.signal})
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var parsed = new DOMParser().parseFromString(html, "text/html");
        var freshBody = parsed.querySelector("#site-results tbody");
        var currentBody = results.querySelector("tbody");
        if (!freshBody || !currentBody) return;
        currentBody.replaceWith(freshBody);
        window.history.replaceState(null, "", url);
        if (showSuggestions && activeInput) {
          var rows = Array.from(freshBody.querySelectorAll("tr"));
          if (activeInput === numberInput) fillSuggestions(numberPanel, numberInput, rows, "data-object-number");
          else fillSuggestions(addressPanel, addressInput, rows, "data-address");
        } else {
          hideSuggestions();
        }
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  function scheduleSearch(input) {
    activeInput = input;
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(function () { refreshResults(true); }, 250);
  }

  numberInput.addEventListener("input", function () { scheduleSearch(numberInput); });
  nameInput.addEventListener("input", function () { activeInput = null; window.clearTimeout(debounceTimer); debounceTimer = window.setTimeout(function () { refreshResults(false); }, 250); });
  addressInput.addEventListener("input", function () { scheduleSearch(addressInput); });
  [numberInput, addressInput].forEach(function (input) {
    input.addEventListener("focus", function () { activeInput = input; });
  });
  form.querySelectorAll('select').forEach(function (input) {
    input.addEventListener("change", function () { activeInput = null; refreshResults(false); });
  });
  form.addEventListener("submit", function (event) { event.preventDefault(); refreshResults(false); });
  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) hideSuggestions();
  });
})();

// Live report search by object name and number.
(function () {
  var form = document.getElementById("report-filter-form");
  var results = document.getElementById("report-results");
  if (!form || !results) return;
  var searchFields = ['site_name', 'site_number'].map(function (name) {
    return form.querySelector('[name="' + name + '"]');
  }).filter(Boolean);
  if (!searchFields.length) return;

  var timer = null;
  var controller = null;
  function refreshReports() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (String(value).trim()) params.set(key, value);
    });
    var url = window.location.pathname + (params.toString() ? "?" + params.toString() : "");
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}, signal: controller.signal})
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var parsed = new DOMParser().parseFromString(html, "text/html");
        var freshResults = parsed.querySelector("#report-results");
        if (!freshResults) return;
        results.replaceWith(freshResults);
        results = freshResults;
        window.history.replaceState(null, "", url);
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  searchFields.forEach(function (field) {
    field.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(refreshReports, 250);
    });
  });
  form.querySelectorAll("select").forEach(function (field) {
    field.addEventListener("change", function () {
      window.clearTimeout(timer);
      refreshReports();
    });
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(timer);
    refreshReports();
  });
})();

// Filter work plans as the object number is typed.
(function () {
  var form = document.getElementById("plan-filter-form");
  var results = document.getElementById("plan-results");
  var liveInputs = form ? ['site_number', 'site_name', 'address'].map(function (name) {
    return form.querySelector('[name="' + name + '"]');
  }).filter(Boolean) : [];
  if (!form || !results || !liveInputs.length) return;

  var timer = null;
  var controller = null;
  function refreshPlans() {
    var params = new URLSearchParams();
    new FormData(form).forEach(function (value, key) {
      if (String(value).trim()) params.set(key, value);
    });
    var url = window.location.pathname + (params.toString() ? "?" + params.toString() : "");
    if (controller) controller.abort();
    controller = new AbortController();
    fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}, signal: controller.signal})
      .then(function (response) { return response.text(); })
      .then(function (html) {
        var parsed = new DOMParser().parseFromString(html, "text/html");
        var freshResults = parsed.querySelector("#plan-results");
        if (!freshResults) return;
        results.replaceWith(freshResults);
        results = freshResults;
        window.history.replaceState(null, "", url);
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  liveInputs.forEach(function (input) {
    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(refreshPlans, 250);
    });
  });
  form.querySelectorAll("select").forEach(function (input) {
    input.addEventListener("change", function () {
      window.clearTimeout(timer);
      refreshPlans();
    });
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(timer);
    refreshPlans();
  });
})();

// Search the site selector on the work plan form by name or object number.
(function () {
  var form = document.getElementById("plan-form");
  var select = form && form.querySelector('[name="site"]');
  if (!select) return;

  var field = select.parentElement;
  var label = field.querySelector('label[for="' + select.id + '"]');
  var input = document.createElement("input");
  input.type = "search";
  input.id = "plan-site-search";
  input.placeholder = "Введите название или номер объекта";
  input.autocomplete = "off";
  input.setAttribute("aria-label", "Поиск объекта по названию или номеру");
  input.required = true;

  var control = document.createElement("div");
  control.className = "site-search-control";
  var toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "site-search-toggle";
  toggle.setAttribute("aria-label", "Показать все объекты");
  toggle.setAttribute("aria-expanded", "false");
  toggle.textContent = "▾";

  var panel = document.createElement("div");
  panel.className = "site-suggestions";
  panel.hidden = true;
  field.classList.add("site-search-field");
  if (label) {
    label.htmlFor = input.id;
    label.textContent = "Объект — поиск по названию или номеру";
  }
  select.insertAdjacentElement("beforebegin", control);
  control.appendChild(input);
  control.appendChild(toggle);
  select.hidden = true;
  select.required = false;
  field.appendChild(panel);

  var initialOption = select.options[select.selectedIndex];
  if (initialOption && initialOption.value) input.value = initialOption.textContent;

  function showMatches(showAll, clearSelection) {
    var query = input.value.trim().toLocaleLowerCase();
    if (clearSelection) {
      select.value = "";
      input.setCustomValidity("");
    }
    panel.replaceChildren();
    if (!query && !showAll) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      return;
    }
    Array.from(select.options).filter(function (option) {
      return option.value && (showAll || option.textContent.toLocaleLowerCase().includes(query));
    }).forEach(function (option) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "site-suggestion";
      button.textContent = option.textContent;
      button.addEventListener("click", function () {
        select.value = option.value;
        input.value = option.textContent;
        input.setCustomValidity("");
        panel.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
      });
      panel.appendChild(button);
    });
    if (!panel.childElementCount) {
      var empty = document.createElement("div");
      empty.className = "site-suggestion muted";
      empty.textContent = "Совпадений не найдено";
      panel.appendChild(empty);
    }
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
  }

  input.addEventListener("input", function () { showMatches(false, true); });
  input.addEventListener("focus", function () {
    if (input.value.trim()) showMatches(false, false);
  });
  toggle.addEventListener("click", function () {
    if (panel.hidden) {
      showMatches(true, false);
      input.focus();
    } else {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });
  form.addEventListener("submit", function (event) {
    if (!select.value) {
      input.setCustomValidity("Выберите объект из списка совпадений.");
      input.reportValidity();
      event.preventDefault();
    }
  });
  document.addEventListener("click", function (event) {
    if (!field.contains(event.target)) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });
})();

// Dynamic document and photo rows.
(function () {
  var docButton = document.getElementById("add-document");
  if (docButton) {
    var docList = document.getElementById("document-inputs");
    var docCount = document.getElementById("document-count");
    var updateCount = function () {
      var count = Number(docList.dataset.existingCount || 0) + Array.from(docList.querySelectorAll('input[type="file"]')).filter(function (el) { return el.files.length > 0; }).length;
      docCount.textContent = "Добавлено: " + count + " из 20";
      docButton.disabled = count >= 20;
    };
    var bindFileName = function (input) {
      input.addEventListener("change", function () {
        var name = input.closest(".file-row").querySelector(".file-name");
        name.textContent = input.files.length ? input.files[0].name : "";
        updateCount();
      });
    };
    docList.querySelectorAll('input[type="file"]').forEach(bindFileName);
    updateCount();
    docButton.addEventListener("click", function () {
      if (docButton.disabled) return;
      var row = document.createElement("div");
      row.className = "file-row";
      var label = document.createElement("label");
      label.appendChild(document.createTextNode("Выберите файл "));
      var input = document.createElement("input");
      input.type = "file";
      input.name = "documents";
      input.accept = "application/pdf,.pdf";
      label.appendChild(input);
      var filename = document.createElement("span");
      filename.className = "file-name muted";
      row.appendChild(label);
      row.appendChild(filename);
      docList.appendChild(row);
      bindFileName(input);
      try {
        if (typeof input.showPicker === "function") input.showPicker();
        else input.click();
      } catch (error) {
        input.click();
      }
    });
  }

  var photoButton = document.getElementById("add-photo");
  if (photoButton) {
    var photoList = document.getElementById("photo-forms");
    var total = document.getElementById("id_photos-TOTAL_FORMS");
    photoButton.addEventListener("click", function () {
      var index = Number(total.value);
      var html = document.getElementById("empty-photo-form").innerHTML.replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      photoList.appendChild(wrapper.firstElementChild);
      total.value = index + 1;
    });
    photoList.addEventListener("click", function (event) {
      if (event.target.classList.contains("remove-photo")) {
        var entries = photoList.querySelectorAll(".photo-entry");
        if (entries.length > 1) event.target.closest(".photo-entry").remove();
      }
    });
  }

  var requirementButton = document.getElementById("add-requirement");
  if (requirementButton) {
    var requirementList = document.getElementById("photo-requirements");
    var requirementTotal = document.getElementById("id_requirements-TOTAL_FORMS");
    var updateRequirementCount = function () {
      var active = Array.from(requirementList.querySelectorAll(".photo-requirement-row")).filter(function (row) {
        var deletion = row.querySelector('input[name$="-DELETE"]');
        return !deletion || !deletion.checked;
      }).length;
      requirementButton.disabled = active >= 20;
    };
    requirementButton.addEventListener("click", function () {
      var index = Number(requirementTotal.value);
      var html = document.getElementById("empty-requirement-form").innerHTML.replace(/__prefix__/g, index);
      var wrapper = document.createElement("div");
      wrapper.innerHTML = html;
      requirementList.appendChild(wrapper.firstElementChild);
      requirementTotal.value = index + 1;
      updateRequirementCount();
    });
    requirementList.addEventListener("click", function (event) {
      if (!event.target.classList.contains("remove-requirement")) return;
      var row = event.target.closest(".photo-requirement-row");
      var deletion = row.querySelector('input[name$="-DELETE"]');
      if (deletion) deletion.checked = true;
      row.hidden = true;
      updateRequirementCount();
    });
    updateRequirementCount();
  }
})();
