// @ts-check
const { themes } = require("prism-react-renderer");

/** @type {import('@docusaurus/types').Config} */
const config = {
  title: "Minutes",
  tagline: "AI Meeting Notes — Open Source, Self-Hosted, Privacy-First",
  favicon: "img/favicon.svg",
  url: "https://manor-os.github.io",
  baseUrl: "/docs/minutes/",
  organizationName: "manor-os",
  projectName: "manor-os.github.io",
  trailingSlash: false,

  onBrokenLinks: "throw",
  onBrokenMarkdownLinks: "warn",

  i18n: {
    defaultLocale: "en",
    locales: ["en"],
  },

  presets: [
    [
      "classic",
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          routeBasePath: "/",
          sidebarPath: "./sidebars.js",
          editUrl: "https://github.com/manor-os/minutes/tree/main/docs/",
        },
        blog: false,
        theme: {
          customCss: "./src/css/custom.css",
        },
      }),
    ],
  ],

  themeConfig:
    /** @type {import('@docusaurus/preset-classic').ThemeConfig} */
    ({
      colorMode: {
        defaultMode: "light",
        respectPrefersColorScheme: true,
      },
      navbar: {
        title: "Minutes",
        logo: {
          alt: "Minutes Logo",
          src: "img/favicon.svg",
        },
        items: [
          {
            type: "docSidebar",
            sidebarId: "docs",
            position: "left",
            label: "Docs",
          },
          {
            href: "https://github.com/manor-os/minutes",
            label: "GitHub",
            position: "right",
          },
        ],
      },
      footer: {
        style: "light",
        links: [
          {
            title: "Docs",
            items: [
              { label: "Getting Started", to: "/" },
              { label: "Configuration", to: "/configuration" },
              { label: "API Reference", to: "/api" },
            ],
          },
          {
            title: "Community",
            items: [
              { label: "GitHub", href: "https://github.com/manor-os/minutes" },
              {
                label: "Issues",
                href: "https://github.com/manor-os/minutes/issues",
              },
            ],
          },
          {
            title: "Manor AI",
            items: [{ label: "Website", href: "https://manorai.xyz" }],
          },
        ],
        copyright: `Copyright © ${new Date().getFullYear()} Manor AI. Built with Docusaurus.`,
      },
      prism: {
        theme: themes.github,
        darkTheme: themes.dracula,
        additionalLanguages: ["bash", "python", "json", "yaml"],
      },
    }),
};

module.exports = config;
