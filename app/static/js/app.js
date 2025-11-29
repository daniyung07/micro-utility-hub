//app.js

// ===================================================================
// 1. UTILITY FUNCTIONS
// ===================================================================

/**
 * Toggles the mobile menu and hamburger state.
 * @param {HTMLElement} hamburger
 * @param {HTMLElement} mobileNavOverlay
 * @param {boolean} [isActive=undefined] - Force a state (true for active, false for closed).
 */
function toggleMobileMenu(hamburger, mobileNavOverlay, isActive) {
    if (!hamburger || !mobileNavOverlay) return;

    // Determine the target state
    const shouldBeActive = isActive !== undefined ? isActive : !hamburger.classList.contains('active');

    hamburger.classList.toggle('active', shouldBeActive);
    mobileNavOverlay.classList.toggle('active', shouldBeActive);
    document.body.classList.toggle('no-scroll', shouldBeActive);
    hamburger.setAttribute('aria-expanded', shouldBeActive);
}

/**
 * Closes the mobile menu and resets states.
 * @param {HTMLElement} hamburger
 * @param {HTMLElement} mobileNavOverlay
 */
function closeMobileMenu(hamburger, mobileNavOverlay) {
    toggleMobileMenu(hamburger, mobileNavOverlay, false);
    // Explicitly focus the hamburger after closing via ESC/link click
    hamburger?.focus();
}

/**
 * Sets up the loading animation on form submission AND submits the form.
 * @param {HTMLFormElement} form
 */
function setupSubmitAnimation(form) {
    if (!form) return;
    const submitButton = form.querySelector('button[type="submit"]');
    if (!submitButton) return;

    form.addEventListener('submit', (e) => {
        // Only proceed if form validation passes
        if (form.checkValidity()) {
            e.preventDefault();

            // Show loading state
            submitButton.innerHTML = '';
            submitButton.disabled = true;
            submitButton.classList.add('loading');

            // Set a short delay for spinner visibility, then submit
            setTimeout(() => {
                form.submit();
            }, 500);
        }
    });
}


// ===================================================================
// 2. MODULE INITIALIZATION FUNCTIONS
// ===================================================================

/**
 * Initializes the header and mobile menu logic.
 */
function initMenu() {
    const hamburger = document.querySelector('.hamburger');
    const mobileNavOverlay = document.querySelector('#mobile-nav-overlay');
    const appHeader = document.getElementById('app-header');

    if (!hamburger || !mobileNavOverlay) return;

    const menuLinks = Array.from(mobileNavOverlay.querySelectorAll('a'));
    let currentIndex = -1;

    // 2.1. Toggle menu on click
    hamburger.addEventListener('click', () => {
        const wasActive = hamburger.classList.contains('active');
        toggleMobileMenu(hamburger, mobileNavOverlay);

        if (!wasActive) { // If opening
            currentIndex = 0;
            menuLinks[currentIndex]?.focus();
        } else { // If closing
            hamburger.focus();
        }
    });

    // 2.2. Close menu on overlay link click or background click
    mobileNavOverlay.addEventListener('click', (e) => {
        if (e.target.closest('a') || e.target === mobileNavOverlay) {
            closeMobileMenu(hamburger, mobileNavOverlay);
        }
    });

    // 2.3. Keyboard Accessibility (ESC to close, Arrow keys for navigation)
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && mobileNavOverlay.classList.contains('active')) {
            closeMobileMenu(hamburger, mobileNavOverlay);
        }

        if (!mobileNavOverlay.classList.contains('active') || menuLinks.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentIndex = (currentIndex + 1) % menuLinks.length;
            menuLinks[currentIndex].focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentIndex = (currentIndex - 1 + menuLinks.length) % menuLinks.length;
            menuLinks[currentIndex].focus();
        }
    });

    // 2.4. Scroll-Triggered Hamburger (fixed on scroll)
    if (appHeader) {
        let headerHeight = appHeader.offsetHeight;
        let isHamburgerFixed = false;

        const toggleFixedHamburger = () => {
            const scrolledDown = window.scrollY > headerHeight;

            if (scrolledDown && !isHamburgerFixed) {
                hamburger.classList.add('fixed-on-scroll');
                isHamburgerFixed = true;
            } else if (!scrolledDown && isHamburgerFixed) {
                hamburger.classList.remove('fixed-on-scroll');
                isHamburgerFixed = false;
            }
        };

        toggleFixedHamburger();
        window.addEventListener('scroll', toggleFixedHamburger);
        window.addEventListener('resize', () => {
            headerHeight = appHeader.offsetHeight;
            toggleFixedHamburger();
        });
    }
}


/**
 * Initializes form submission animations for specific forms.
 */
function initForms() {
    const formsToAnimate = [
        document.querySelector('form[action$="/shortener/create"]'),
        document.querySelector('form[action$="/tasks/new"]')
    ].filter(form => form !== null);

    formsToAnimate.forEach(setupSubmitAnimation);
}

/**
 * Initializes smooth scrolling for anchor links within the app.
 */
function initSmoothScroll() {
    document.addEventListener('click', (e) => {
        const anchor = e.target.closest('nav a, #mobile-nav-overlay a');
        const href = anchor?.getAttribute('href');

        if (href?.startsWith('#')) {
            e.preventDefault();
            const target = document.querySelector(href);
            if (target) {
                target.scrollIntoView({ behavior: 'smooth' });
            }
        }
    });
}

/**
 * Initializes the image cropping modal logic using the Cropper library.
 */
function initCropper() {
    const Cropper = window.Cropper;

    const imageUploadInput = document.getElementById('image-upload-input');
    const imageToCrop = document.getElementById('image-to-crop');
    const croppedDataInput = document.getElementById('cropped-image-data-uri');
    const cropModal = document.getElementById('crop-modal');
    const saveCropButton = document.querySelector('#crop-modal button[data-action="save"]');
    const cancelCropButton = document.querySelector('#crop-modal button[data-action="cancel"]');
    const cropperControls = document.querySelector('.cropper-controls');

    if (!imageUploadInput || typeof Cropper === 'undefined') {
        return;
    }

    let cropperInstance = null;

    const destroyCropper = () => {
        if (cropperInstance) {
            cropperInstance.destroy();
            cropperInstance = null;
        }
    };

    const hideModal = () => {
        if (cropModal) cropModal.classList.remove('active');
        destroyCropper();
    };

    imageUploadInput.addEventListener('change', (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = ev => {
            if (imageToCrop && cropModal && cropperControls) {
                imageToCrop.src = ev.target?.result;
                cropModal.classList.add('active');
                cropperControls.style.display = 'flex';

                destroyCropper();
                try {
                    cropperInstance = new Cropper(imageToCrop, {
                        aspectRatio: 1,
                        viewMode: 1,
                        responsive: true,
                        minCropBoxWidth: 100,
                        ready() {}
                    });
                } catch (error) {
                    console.error('Error initializing Cropper:', error);
                    hideModal();
                }
            } else {
                console.error('Cropper modal elements not found.');
            }
        };
        reader.onerror = (err) => {
             console.error('FileReader error:', err);
        };
        reader.readAsDataURL(file);
    });

    if (saveCropButton) {
        saveCropButton.addEventListener('click', () => {
            if (!cropperInstance || !croppedDataInput) return;
            try {
                const canvas = cropperInstance.getCroppedCanvas({});
                croppedDataInput.value = canvas.toDataURL('image/jpeg', 0.8);
                hideModal();
            } catch (error) {
                console.error('Error getting cropped canvas:', error);
                hideModal();
            }
        });
    }

    if (cancelCropButton) {
        cancelCropButton.addEventListener('click', () => {
            hideModal();
            if (imageUploadInput) imageUploadInput.value = ''; // Clear input for re-upload
        });
    }
}

// ===================================================================
// 3. MAIN APP INITIALIZATION
// ===================================================================

/**
 * Handles the initial page loading overlay animation.
 */
function initLoadingOverlay() {
    const loadingOverlay = document.querySelector('#loading-overlay');
    if (loadingOverlay) {
        loadingOverlay.classList.remove('hidden');
        setTimeout(() => {
            loadingOverlay.classList.add('fade-out');
            setTimeout(() => loadingOverlay.classList.add('hidden'), 200);
        }, 1000); // Show for 1 second
    }
}


document.addEventListener('DOMContentLoaded', () => {

    // 3.1. General UI Initializations
    initLoadingOverlay();
    initMenu();
    initSmoothScroll();

    // 3.2. Feature-Specific Initializations
    initForms();
    initCropper();
    initChatbotWidget(); // <-- Chatbot JS is now called here
});