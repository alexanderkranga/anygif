// Navbar scroll effect + blur when mobile menu is open
const navbar = document.querySelector('.navbar');
const navCollapse = document.querySelector('.navbar-collapse');

function updateNavbar() {
  const menuOpen = navCollapse && navCollapse.classList.contains('show');
  navbar.classList.toggle('scrolled', window.scrollY > 40 || menuOpen);
}

if (navbar) {
  window.addEventListener('scroll', updateNavbar, { passive: true });

  if (navCollapse) {
    navCollapse.addEventListener('show.bs.collapse', () => {
      navbar.classList.add('scrolled');
    });
    navCollapse.addEventListener('hidden.bs.collapse', updateNavbar);
  }
}

// Close mobile nav on link click
const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
navLinks.forEach(link => {
  link.addEventListener('click', () => {
    if (navCollapse && navCollapse.classList.contains('show')) {
      bootstrap.Collapse.getInstance(navCollapse)?.hide();
    }
  });
});

// Smooth reveal on scroll
const revealEls = document.querySelectorAll('.reveal');
if (revealEls.length) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15 });
  revealEls.forEach(el => observer.observe(el));
}
