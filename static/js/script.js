document.addEventListener("DOMContentLoaded", () => {
  // --- Deepfake Detector ---
  const detectBtn = document.getElementById("detectBtn");
  if (detectBtn) {
    const urlInput = document.getElementById("urlInput");
    const deepfakeResultBox = document.getElementById("result");

    detectBtn.addEventListener("click", async () => {
      const url = urlInput.value.trim();
      deepfakeResultBox.style.display = "block";
      deepfakeResultBox.className = "alert";

      if (!url) {
        deepfakeResultBox.className = "alert alert-danger";
        deepfakeResultBox.innerHTML = "⚠️ Please paste a URL before clicking Detect.";
        return;
      }

      deepfakeResultBox.className = "alert alert-info";
      deepfakeResultBox.innerHTML = "⏳ Checking...";

      try {
        const res = await fetch(`/analyze/url?url=${encodeURIComponent(url)}`);
        const data = await res.json();

        if (!res.ok) {
          deepfakeResultBox.className = "alert alert-danger";
          deepfakeResultBox.innerHTML = data.error || "Something went wrong";
          return;
        }

        let circleColor = data.label === "REAL" ? "green" : "red";

        deepfakeResultBox.className =
          data.label === "REAL" ? "alert alert-success" : "alert alert-danger";

        deepfakeResultBox.innerHTML = `
          <div class="row align-items-center">
            <!-- Preview -->
            <div class="col-md-3 text-center">
              <img src="${data.preview}" alt="Preview" class="img-thumbnail" style="max-width: 100%; height: auto;">
            </div>

            <!-- Info -->
            <div class="col-md-6">
              <p class="mb-2"><b>Domain:</b> ${data.domain}</p>
              <p class="mb-0"><b>Type:</b> ${data.type}</p>
            </div>

            <!-- Gauge -->
            <div class="col-md-3 text-center d-flex flex-column align-items-center justify-content-center">
              <svg width="80" height="80" class="mb-2">
                <circle cx="40" cy="40" r="30" stroke="#ddd" stroke-width="8" fill="none" />
                <circle cx="40" cy="40" r="30" stroke="${circleColor}" stroke-width="8" fill="none"
                  stroke-dasharray="188.4"
                  stroke-dashoffset="0"
                  transform="rotate(-90 40 40)" />
                <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="14" fill="${circleColor}" font-weight="bold">
                  ${data.label}
                </text>
              </svg>  
              <small class="text-muted">Result</small>  
            </div>
          </div>
        `;
      } catch (err) {
        deepfakeResultBox.className = "alert alert-danger";
        deepfakeResultBox.innerHTML = "❌ Error: " + err.message;
      }
    });
  }

  // --- Plagiarism Checker ---
  const plagBtn = document.getElementById("plagBtn");
  if (plagBtn) {
    const plagInput = document.getElementById("plagInput");
    const plagFile = document.getElementById("plagFile");
    const plagResultBox = document.getElementById("plagResult");

    plagBtn.addEventListener("click", async () => {
      const text = plagInput ? plagInput.value.trim() : "";
      const file = plagFile ? plagFile.files[0] : null;

      plagResultBox.style.display = "block";
      plagResultBox.className = "alert";

      if (!text && !file) {
        plagResultBox.className = "alert alert-danger";
        plagResultBox.innerHTML = "⚠️ Please paste text or upload a document before checking.";
        return;
      }

      plagResultBox.className = "alert alert-info";
      plagResultBox.innerHTML = "⏳ Checking...";

      try {
        let res;
        if (file) {
          const formData = new FormData();
          formData.append("file", file);

          res = await fetch("/analyze/plag", {
            method: "POST",
            body: formData,
          });
        } else {
          res = await fetch("/analyze/plag", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
          });
        }

        const data = await res.json();

        if (!res.ok) {
          plagResultBox.className = "alert alert-danger";
          plagResultBox.innerHTML = data.error || "Something went wrong";
          return;
        }

        const summary = data.summary;
        const results = data.results;
        const plagColor = summary.plag_percent > 50 ? "red" : "green";

        let html = `
          <div class="row align-items-center">
            <div class="col-md-3 text-center d-flex justify-content-center">
              <div class="progress-circle" 
                   style="width:100px; height:100px; border-radius:50%; border:8px solid ${plagColor}; display:flex; justify-content:center; align-items:center; font-weight:bold; margin: 0 auto;">
                ${summary.plag_percent}%
              </div>
            </div>
            <div class="col-md-9" style="padding-left: 20px;">
              <b>Plagiarism:</b> ${summary.plag_percent}%<br>
              <b>Original:</b> ${summary.original_percent}%<br>
            </div>
          </div>
          <hr>
          <div><b>Detailed Report:</b></div>
        `;

        results.forEach(r => {
          let color = r.label.startsWith("PLAGIARISM") ? "#ffcccc" : "#ccffcc";
          let border = r.label.startsWith("PLAGIARISM") ? "2px solid red" : "1px solid #aaa";
          html += `
            <div style="background:${color}; border:${border}; padding:8px; margin:6px 0; border-radius:5px;">
              ${r.paragraph}<br>
              <small><i>${r.label}${r.web_source ? ` → <a href="${r.web_source}" target="_blank">Source</a>` : ""}</i></small>
            </div>
          `;
        });

        plagResultBox.className = "alert alert-light";
        plagResultBox.innerHTML = html;
      } catch (err) {
        plagResultBox.className = "alert alert-danger";
        plagResultBox.innerHTML = "❌ Error: " + err.message;
      }
    });
  }
});
