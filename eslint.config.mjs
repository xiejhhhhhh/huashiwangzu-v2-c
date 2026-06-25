import pluginVue from 'eslint-plugin-vue'
import parserVue from 'vue-eslint-parser'

export default [
  {
    ignores: ['**/dist/**', '**/node_modules/**', '**/__pycache__/**', '**/*.generated.*', '**/.venv/**'],
  },
  {
    files: ['frontend/src/**/*.ts', 'frontend/src/**/*.vue', 'modules/*/frontend/**/*.ts', 'modules/*/frontend/**/*.vue'],
    languageOptions: {
      parser: parserVue,
      parserOptions: {
        parser: {
          ts: '@typescript-eslint/parser',
          js: 'espree',
        },
      },
    },
    plugins: {
      vue: pluginVue,
    },
    rules: {
      ...pluginVue.configs['flat/essential'].rules,
      'no-alert': 'error',
    },
  },
]
