//auth.js

// ===================================================================
// 1. PASSWORD STRENGTH UTILITIES
// ===================================================================

/**
 * Calculates a password strength score (0-4).
 * @param {string} password
 * @returns {number}
 */
function calculatePasswordStrength(password) {
    let score = 0;
    // Check for length > 7
    if (password.length > 7) score++;
    // Check for uppercase
    if (/[A-Z]/.test(password)) score++;
    // Check for numbers
    if (/[0-9]/.test(password)) score++;
    // Check for special characters
    if (/[^A-Za-z0-9]/.test(password)) score++;
    return score;
}

/**
 * Updates the UI elements based on password strength.
 * This is designed to work with the elements in register.html.
 * @param {HTMLInputElement} passwordField
 */
function updatePasswordStrength(passwordField) {
    const strengthBar = document.querySelector('#password-strength-bar');
    const strengthText = document.querySelector('#password-strength-text');
    const strengthMeter = document.querySelector('#password-strength-meter');

    if (!passwordField || !strengthBar || !strengthText || !strengthMeter) return;

    const password = passwordField.value;
    const score = calculatePasswordStrength(password);
    const width = (score / 4) * 100;

    let color, text;

    if (password.length === 0) {
        color = 'transparent';
        text = '';
        strengthMeter.style.visibility = 'hidden';
    } else {
        strengthMeter.style.visibility = 'visible';

        if (score < 2) {
            color = '#dc3545'; // Red (Weak)
            text = 'Weak';
        } else if (score === 2) {
            color = '#ffc107'; // Yellow (Moderate)
            text = 'Moderate';
        } else {
            color = '#28a745'; // Green (Strong)
            text = 'Strong';
        }
    }

    strengthBar.style.width = `${width}%`;
    strengthBar.style.backgroundColor = color;
    strengthText.textContent = text;
    strengthText.style.color = color;
}


// ===================================================================
// 2. MAIN AUTH LOGIC
// ===================================================================

document.addEventListener('DOMContentLoaded', () => {

    // --- 2.1. Password Toggle ---
    const passwordToggles = document.querySelectorAll('.password-toggle');
    passwordToggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const target = document.getElementById(toggle.dataset.target);
            if (!target) return;

            const type = target.type === 'password' ? 'text' : 'password';
            target.type = type;

            // Switch icon between eye and masked eye
            toggle.textContent = type === 'password' ? '👁️' : '🙈';
        });
    });

    // --- 2.2. Password Strength Meter Activation (Registration Page) ---
    const registerPasswordField = document.querySelector('#password-field');

    if (registerPasswordField) {
        // Hide meter initially
        const strengthMeter = document.querySelector('#password-strength-meter');
        if (strengthMeter) strengthMeter.style.visibility = 'hidden';

        // Bind input event to the password field
        registerPasswordField.addEventListener('input', () => updatePasswordStrength(registerPasswordField));

        // Also run once on load to handle pre-filled forms (optional, but robust)
        updatePasswordStrength(registerPasswordField);
    }
});