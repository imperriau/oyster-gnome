// SPDX-License-Identifier: GPL-3.0-or-later
// GNOME's shared config, as used by gnome-shell-extensions, plus the GJS globals the extension uses.

import {defineConfig} from 'eslint/config';
import gnome from 'eslint-config-gnome';

export default defineConfig([
    gnome.configs.recommended,
    {
        files: ['extension/**/*.js'],
        languageOptions: {
            ecmaVersion: 2024,
            sourceType: 'module',
            globals: {
                console: 'readonly',
                global: 'readonly',
            },
        },
    },
]);
