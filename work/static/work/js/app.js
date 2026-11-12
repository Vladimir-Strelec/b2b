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
      var preview = area.querySelector(".photo-upload-preview");
      var camera = area.querySelector(".photo-camera-icon");
      if (!label || !filename || !preview || !camera) return;
      if (field.files && field.files.length) {
        var photo = field.files[0];
        if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
        preview.dataset.objectUrl = URL.createObjectURL(photo);
        preview.src = preview.dataset.objectUrl;
        preview.hidden = false;
        camera.hidden = true;
        label.querySelector(".photo-upload-title").textContent = "Заменить фотографию";
        filename.textContent = photo.name;
        label.classList.add("has-file");
      } else {
        if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
        delete preview.dataset.objectUrl;
        preview.removeAttribute("src");
        preview.hidden = true;
        camera.hidden = false;
        label.querySelector(".photo-upload-title").textContent = "Добавить фотографию";
        filename.textContent = "Нажмите, чтобы выбрать файл";
        label.classList.remove("has-file");
      }
    });
  });
})();

// Keep selected work photos in place when a submission has validation errors.
(function () {
  var form = document.getElementById("submission-form");
  if (!form) return;
  var feedback = document.getElementById("submission-form-feedback");

  function clearErrors() {
    form.querySelectorAll(".is-invalid").forEach(function (field) {
      field.classList.remove("is-invalid");
      field.removeAttribute("aria-invalid");
    });
    form.querySelectorAll(".submission-inline-error").forEach(function (error) { error.remove(); });
    feedback.hidden = true;
    feedback.textContent = "";
  }
  function markInvalid(field, message) {
    if (!field) return;
    field.classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    var host;
    if (field.classList.contains("photo-file-input")) {
      host = field.closest(".photo-upload-area");
      var label = host && host.querySelector(".photo-upload-control");
      if (label) label.classList.add("is-invalid");
    } else {
      host = field.parentElement;
    }
    var error = document.createElement("small");
    error.className = "submission-inline-error";
    error.textContent = message;
    host.appendChild(error);
  }
  function showFeedback(message) {
    feedback.textContent = message;
    feedback.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearErrors();
    var invalid = [];
    form.querySelectorAll(".photo-entry").forEach(function (entry) {
      var image = entry.querySelector(".photo-file-input");
      var description = entry.querySelector(".photo-description-input");
      if (image && !(image.files && image.files.length) && entry.dataset.hasSavedImage !== "true") {
        markInvalid(image, "Добавьте фотографию в это поле.");
        invalid.push(image);
      }
      if (description && !description.value.trim()) {
        markInvalid(description, "Опишите, что сделано на этом фото.");
        invalid.push(description);
      }
    });
    if (invalid.length) {
      showFeedback("Заполните выделенные поля. Выбранные фотографии останутся на месте.");
      invalid[0].scrollIntoView({behavior: "smooth", block: "center"});
      invalid[0].focus({preventScroll: true});
      return;
    }

    var submitButton = form.querySelector('button[type="submit"]');
    var originalLabel = submitButton ? submitButton.textContent : "";
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Отправка…";
    }
    fetch(form.action || window.location.href, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: {"X-Requested-With": "XMLHttpRequest"}
    }).then(function (response) {
      if (response.redirected) {
        window.location.assign(response.url);
        return null;
      }
      return response.text();
    }).then(function (html) {
      if (html === null) return;
      var parsed = new DOMParser().parseFromString(html, "text/html");
      var returnedForm = parsed.getElementById("submission-form");
      if (!returnedForm) {
        showFeedback("Отчёт не отправлен. Проверьте соединение и попробуйте ещё раз.");
        return;
      }
      var globalErrors = [];
      returnedForm.querySelectorAll(".errorlist").forEach(function (list) {
        var messages = Array.from(list.querySelectorAll("li")).map(function (li) { return li.textContent.trim(); }).filter(Boolean);
        if (!messages.length) return;
        var fieldName = null;
        if (!list.classList.contains("nonfield") && !list.classList.contains("nonform")) {
          var parent = list.parentElement;
          while (parent && parent !== returnedForm) {
            var controls = parent.querySelectorAll('input[name], select[name], textarea[name]');
            if (controls.length === 1) {
              fieldName = controls[0].name;
              break;
            }
            parent = parent.parentElement;
          }
        }
        if (fieldName) {
          var currentField = Array.from(form.querySelectorAll('[name]')).find(function (field) { return field.name === fieldName; });
          messages.forEach(function (message) { markInvalid(currentField, message); });
        } else {
          globalErrors = globalErrors.concat(messages);
        }
      });
      globalErrors = Array.from(new Set(globalErrors));
      showFeedback(globalErrors.length ? globalErrors.join(" ") : "Отчёт не отправлен. Проверьте выделенные поля.");
      var firstInvalid = form.querySelector(".is-invalid");
      if (firstInvalid) {
        firstInvalid.scrollIntoView({behavior: "smooth", block: "center"});
        firstInvalid.focus({preventScroll: true});
      }
    }).catch(function () {
      showFeedback("Не удалось отправить отчёт. Проверьте соединение; выбранные фото и описания сохранены.");
    }).finally(function () {
      if (submitButton && document.body.contains(submitButton)) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel;
      }
    });
  });
})();

// Search objects by name, number, or address in one field with suggestions.
(function () {
  var form = document.getElementById("site-filter-form");
  var results = document.getElementById("site-results");
  if (!form || !results) return;

  var input = form.querySelector('[name="site_search"]');
  var panel = form.querySelector(".site-suggestions");
  var toggle = form.querySelector(".site-search-toggle");
  if (!input || !panel || !toggle) return;

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
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  function fillSuggestions(rows) {
    panel.replaceChildren();
    var seen = new Set();
    rows.forEach(function (row) {
      var cell = row.querySelector("[data-object-number]");
      var addressCell = row.querySelector("[data-address]");
      if (!cell || !addressCell) return;
      var number = cell.dataset.objectNumber;
      var name = row.cells[1] ? row.cells[1].innerText.split("\n")[0].trim() : "Объект";
      var key = number || (name + "|" + addressCell.dataset.address);
      if (seen.has(key)) return;
      seen.add(key);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "site-suggestion";
      button.textContent = name;
      var detail = document.createElement("small");
      detail.textContent = (number ? "№ " + number + " · " : "") + addressCell.dataset.address;
      button.appendChild(detail);
      button.addEventListener("click", function () {
        input.value = number || name;
        hideSuggestions();
        refreshResults(false);
        input.focus();
      });
      panel.appendChild(button);
    });
    panel.hidden = panel.childElementCount === 0;
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
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
        if (showSuggestions) {
          fillSuggestions(Array.from(freshBody.querySelectorAll("tr")));
        } else {
          hideSuggestions();
        }
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  function scheduleSearch() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(function () { refreshResults(true); }, 250);
  }

  input.addEventListener("input", scheduleSearch);
  input.addEventListener("focus", function () {
    if (input.value.trim()) scheduleSearch();
  });
  form.querySelectorAll('select').forEach(function (input) {
    input.addEventListener("change", function () { refreshResults(false); });
  });
  form.addEventListener("submit", function (event) { event.preventDefault(); refreshResults(false); });
  toggle.addEventListener("click", function () {
    window.clearTimeout(debounceTimer);
    input.value = "";
    refreshResults(true);
    input.focus();
  });
  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) hideSuggestions();
  });
})();

// Live report search by object name, number, and address.
(function () {
  var form = document.getElementById("report-filter-form");
  var results = document.getElementById("report-results");
  if (!form || !results) return;
  var input = form.querySelector('[name="site_search"]');
  var panel = form.querySelector(".site-suggestions");
  var toggle = form.querySelector(".site-search-toggle");
  var optionsNode = document.getElementById("report-site-options");
  if (!input || !panel || !toggle || !optionsNode) return;
  var sites = JSON.parse(optionsNode.textContent || "[]");

  var timer = null;
  var controller = null;
  function hideSuggestions() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }
  function showSuggestions() {
    var query = input.value.trim().toLocaleLowerCase();
    panel.replaceChildren();
    sites.filter(function (site) {
      var searchable = [site.name, site.object_number, site.address].join(" ").toLocaleLowerCase();
      return !query || searchable.includes(query);
    }).slice(0, 100).forEach(function (site) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "site-suggestion";
      button.textContent = site.name;
      var detail = document.createElement("small");
      detail.textContent = (site.object_number ? "№ " + site.object_number + " · " : "") + site.address;
      button.appendChild(detail);
      button.addEventListener("click", function () {
        input.value = site.object_number || site.name;
        hideSuggestions();
        refreshReports(false);
      });
      panel.appendChild(button);
    });
    panel.hidden = panel.childElementCount === 0;
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
  }
  function refreshReports(showOptions) {
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
        if (showOptions) showSuggestions();
        else hideSuggestions();
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  input.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () { refreshReports(true); }, 250);
  });
  form.querySelectorAll("select").forEach(function (field) {
    field.addEventListener("change", function () {
      window.clearTimeout(timer);
      refreshReports(false);
    });
  });
  form.querySelectorAll('input[type="date"]').forEach(function (field) {
    field.addEventListener("change", function () { refreshReports(false); });
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(timer);
    refreshReports(false);
  });
  toggle.addEventListener("click", function () {
    input.value = "";
    showSuggestions();
    input.focus();
  });
  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) hideSuggestions();
  });
})();

// Filter work plans by object name, number, or address.
(function () {
  var form = document.getElementById("plan-filter-form");
  var results = document.getElementById("plan-results");
  var input = form && form.querySelector('[name="site_search"]');
  var panel = form && form.querySelector(".site-suggestions");
  var toggle = form && form.querySelector(".site-search-toggle");
  var optionsNode = document.getElementById("plan-site-options");
  if (!form || !results || !input || !panel || !toggle || !optionsNode) return;
  var sites = JSON.parse(optionsNode.textContent || "[]");

  var timer = null;
  var controller = null;
  function hideSuggestions() {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }
  function showSuggestions() {
    var query = input.value.trim().toLocaleLowerCase();
    panel.replaceChildren();
    sites.filter(function (site) {
      var searchable = [site.name, site.object_number, site.address].join(" ").toLocaleLowerCase();
      return !query || searchable.includes(query);
    }).slice(0, 100).forEach(function (site) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "site-suggestion";
      button.textContent = site.name;
      var detail = document.createElement("small");
      detail.textContent = (site.object_number ? "№ " + site.object_number + " · " : "") + site.address;
      button.appendChild(detail);
      button.addEventListener("click", function () {
        input.value = site.object_number || site.name;
        hideSuggestions();
        refreshPlans(false);
      });
      panel.appendChild(button);
    });
    panel.hidden = panel.childElementCount === 0;
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
  }
  function refreshPlans(showOptions) {
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
        if (showOptions) showSuggestions();
        else hideSuggestions();
      })
      .catch(function (error) {
        if (error.name !== "AbortError") window.location.assign(url);
      });
  }

  input.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () { refreshPlans(true); }, 250);
  });
  form.querySelectorAll("select").forEach(function (input) {
    input.addEventListener("change", function () {
      window.clearTimeout(timer);
      refreshPlans(false);
    });
  });
  form.querySelectorAll('input[type="date"]').forEach(function (input) {
    input.addEventListener("change", function () { refreshPlans(false); });
  });
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    window.clearTimeout(timer);
    refreshPlans(false);
  });
  toggle.addEventListener("click", function () {
    input.value = "";
    showSuggestions();
    input.focus();
  });
  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) hideSuggestions();
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

// Validate object forms before upload and keep the selected files on server errors.
(function () {
  var form = document.getElementById("site-form");
  if (!form) return;
  var feedback = document.getElementById("site-form-feedback");

  function clearErrors() {
    form.querySelectorAll(".is-invalid").forEach(function (field) {
      field.classList.remove("is-invalid");
      field.removeAttribute("aria-invalid");
    });
    form.querySelectorAll(".site-inline-error").forEach(function (error) { error.remove(); });
    feedback.hidden = true;
    feedback.textContent = "";
  }
  function markInvalid(field, message) {
    if (!field) return;
    field.classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    var container = field.closest(".photo-requirement-row, .file-row") || field.parentElement;
    var error = document.createElement("small");
    error.className = "site-inline-error";
    error.textContent = message;
    container.appendChild(error);
  }
  function showFeedback(message) {
    feedback.textContent = message;
    feedback.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    clearErrors();
    var invalid = [];
    [
      [form.elements.object_number, "Введите номер объекта."],
      [form.elements.name, "Введите название объекта."],
      [form.elements.address, "Введите адрес объекта."],
      [form.elements.site_type, "Выберите тип объекта."],
    ].forEach(function (item) {
      if (item[0] && !String(item[0].value).trim()) {
        markInvalid(item[0], item[1]);
        invalid.push(item[0]);
      }
    });

    var requirementList = document.getElementById("photo-requirements");
    if (requirementList) {
      var rows = Array.from(requirementList.querySelectorAll(".photo-requirement-row")).filter(function (row) {
        var deletion = row.querySelector('input[name$="-DELETE"]');
        return !row.hidden && (!deletion || !deletion.checked);
      });
      if (!rows.length) {
        var addRequirement = document.getElementById("add-requirement");
        markInvalid(addRequirement, "Добавьте хотя бы одно обязательное фото-поле.");
        invalid.push(addRequirement);
      }
      rows.forEach(function (row) {
        var category = row.querySelector('select[name$="-category"]');
        if (category && !category.value) {
          markInvalid(category, "Выберите категорию этого фото.");
          invalid.push(category);
        }
      });
    }

    var docList = document.getElementById("document-inputs");
    if (docList) {
      var fileInputs = Array.from(docList.querySelectorAll('input[type="file"]'));
      var selectedFiles = fileInputs.reduce(function (all, input) { return all.concat(Array.from(input.files || [])); }, []);
      var existingCount = Number(docList.dataset.existingCount || 0);
      if (!existingCount && !selectedFiles.length) {
        var firstFile = fileInputs[0];
        markInvalid(firstFile, "Прикрепите хотя бы один файл PDF или Excel.");
        invalid.push(firstFile);
      }
      if (existingCount + selectedFiles.length > 20) {
        markInvalid(fileInputs[0], "Можно прикрепить не более 20 файлов.");
        invalid.push(fileInputs[0]);
      }
      selectedFiles.forEach(function (file) {
        if (!/\.(pdf|xls|xlsx)$/i.test(file.name)) {
          var field = fileInputs.find(function (input) { return Array.from(input.files || []).includes(file); });
          markInvalid(field, "Поддерживаются только PDF и Excel (.xls, .xlsx).");
          invalid.push(field);
        }
      });
    }

    if (invalid.length) {
      showFeedback("Заполните выделенные поля. Введённые данные и выбранные файлы сохранены.");
      invalid[0].scrollIntoView({behavior: "smooth", block: "center"});
      invalid[0].focus({preventScroll: true});
      return;
    }

    var submitButton = form.querySelector('button[type="submit"]');
    var originalLabel = submitButton ? submitButton.textContent : "";
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Сохранение…";
    }
    fetch(form.action || window.location.href, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: {"X-Requested-With": "XMLHttpRequest"}
    }).then(function (response) {
      if (response.redirected) {
        window.location.assign(response.url);
        return null;
      }
      return response.text();
    }).then(function (html) {
      if (html === null) return;
      var parsed = new DOMParser().parseFromString(html, "text/html");
      var returnedForm = parsed.getElementById("site-form");
      if (!returnedForm) {
        showFeedback("Не удалось сохранить объект. Проверьте соединение и попробуйте ещё раз.");
        return;
      }
      var globalErrors = [];
      returnedForm.querySelectorAll(".errorlist").forEach(function (list) {
        var messages = Array.from(list.querySelectorAll("li")).map(function (li) { return li.textContent.trim(); }).filter(Boolean);
        if (!messages.length) return;
        var fieldName = null;
        if (!list.classList.contains("nonfield") && !list.classList.contains("nonform")) {
          var parent = list.parentElement;
          while (parent && parent !== returnedForm) {
            var controls = parent.querySelectorAll('input[name], select[name], textarea[name]');
            if (controls.length === 1) {
              fieldName = controls[0].name;
              break;
            }
            parent = parent.parentElement;
          }
        }
        if (fieldName) {
          var currentField = Array.from(form.querySelectorAll('[name]')).find(function (field) { return field.name === fieldName; });
          messages.forEach(function (message) { markInvalid(currentField, message); });
        } else {
          globalErrors = globalErrors.concat(messages);
        }
      });
      globalErrors = Array.from(new Set(globalErrors));
      showFeedback(globalErrors.length ? globalErrors.join(" ") : "Проверьте выделенные поля.");
      var firstInvalid = form.querySelector(".is-invalid");
      if (firstInvalid) {
        firstInvalid.scrollIntoView({behavior: "smooth", block: "center"});
        firstInvalid.focus({preventScroll: true});
      }
    }).catch(function () {
      showFeedback("Не удалось отправить форму. Проверьте соединение; введённые данные и файлы сохранены.");
    }).finally(function () {
      if (submitButton && document.body.contains(submitButton)) {
        submitButton.disabled = false;
        submitButton.textContent = originalLabel;
      }
    });
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
        var status = input.closest(".file-row").querySelector(".file-upload-status");
        name.textContent = input.files.length ? input.files[0].name : "";
        status.textContent = input.files.length ? "Файл добавлен" : "";
        input.classList.remove("is-invalid");
        var oldError = input.closest(".file-row").querySelector(".site-inline-error");
        if (oldError) oldError.remove();
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
      var status = document.createElement("span");
      status.className = "file-upload-status";
      status.setAttribute("aria-live", "polite");
      row.appendChild(label);
      row.appendChild(filename);
      row.appendChild(status);
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
