/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        fantasy: {
          bg: "#0f0e14",
          panel: "#1a1824",
          border: "#3d3550",
          gold: "#c9a227",
          accent: "#7b5ea7",
          text: "#e8e0d5",
          muted: "#9a8f82",
        },
      },
      fontFamily: {
        fantasy: ["Georgia", "Cambria", "Times New Roman", "serif"],
      },
      animation: {
        "dice-shake": "diceShake 0.5s ease-in-out",
        "dice-pop": "dicePop 0.3s ease-out",
      },
      keyframes: {
        diceShake: {
          "0%, 100%": { transform: "rotate(0deg) scale(1)" },
          "25%": { transform: "rotate(-12deg) scale(1.1)" },
          "75%": { transform: "rotate(12deg) scale(1.1)" },
        },
        dicePop: {
          "0%": { transform: "scale(0.5)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
