export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      boxShadow: {
        soft: "0 18px 60px rgba(15, 23, 42, 0.08)",
        hairline: "0 1px 0 rgba(15, 23, 42, 0.06)",
      },
      colors: {
        ink: "#0b0c0f",
        mist: "#f5f6f8",
        line: "#e7e9ee",
        appleBlue: "#0069ff",
        risk: "#f59e0b",
        danger: "#dc2626",
      },
    },
  },
  plugins: [],
};
