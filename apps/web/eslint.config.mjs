import core from "eslint-config-next/core-web-vitals";
import ts from "eslint-config-next/typescript";

const config = [{ ignores: [".next/**", "out/**", "next-env.d.ts"] }, ...core, ...ts];

export default config;
