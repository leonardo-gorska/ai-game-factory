export default [
    {
        files: ["src/**/*.js"],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: {
                Phaser: "readonly",
                window: "readonly",
                document: "readonly",
                console: "readonly",
                setTimeout: "readonly",
                setInterval: "readonly",
                clearTimeout: "readonly",
                clearInterval: "readonly",
                requestAnimationFrame: "readonly",
            },
        },
        rules: {
            "no-undef": "error",
            "no-unused-vars": "warn",
            "no-unreachable": "error",
            "no-constant-condition": "warn",
            "no-dupe-keys": "error",
            "no-duplicate-case": "error",
            "no-empty": "warn",
            "no-func-assign": "error",
            "no-inner-declarations": "error",
            "valid-typeof": "error",
        },
    },
];
