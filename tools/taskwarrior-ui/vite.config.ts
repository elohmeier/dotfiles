import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

const out = '../../scripts/taskwarrior_ui';

export default defineConfig({
	plugins: [sveltekit({ adapter: adapter({ pages: out, assets: out, fallback: 'index.html' }) })],
	server: { proxy: { '/api': 'http://127.0.0.1:8066' } }
});
