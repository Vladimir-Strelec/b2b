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
})();
