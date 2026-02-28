/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out forwards',
        'slide-up': 'slideUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'shake': 'shake 0.6s ease-in-out',
        'glow': 'glow 2s ease-in-out infinite',
        'aurora-1': 'aurora1 20s ease-in-out infinite',
        'aurora-2': 'aurora2 25s ease-in-out infinite',
        'aurora-3': 'aurora3 22s ease-in-out infinite',
        'text-shine': 'text-shine 6s ease-in-out infinite',
        'hero-glitch': 'hero-glitch 10s linear 3s infinite',
        'pulse-ring': 'pulse-ring 2s ease-out infinite',
        'logo-morph': 'logo-morph 8s ease-in-out infinite',
        'metric-glow': 'metric-glow 3s ease-in-out infinite',
        'upload-pulse': 'upload-pulse 2s ease-in-out infinite',
        'drop-glow': 'drop-glow 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
