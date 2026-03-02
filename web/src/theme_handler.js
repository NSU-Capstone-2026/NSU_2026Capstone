document.addEventListener("DOMContentLoaded", function () {
  const savedTheme = localStorage.getItem("color-theme") || "dark";
  document.documentElement.setAttribute("color-theme", savedTheme);
});

const toggleButton = document.querySelector('.dark-light-toggle');

if (toggleButton) {
    toggleButton.addEventListener('click', () => {      
      const currentTheme = document.documentElement.getAttribute("color-theme");
      const newTheme = currentTheme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("color-theme", newTheme);
      localStorage.setItem("color-theme", newTheme);
    });
}
