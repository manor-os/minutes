/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    'index',
    {
      type: 'category',
      label: 'Getting Started',
      items: ['getting-started/installation', 'getting-started/local-mode', 'getting-started/cloud-api'],
    },
    {
      type: 'category',
      label: 'Features',
      items: ['features/recording', 'features/templates', 'features/search', 'features/sharing', 'features/chat', 'features/webhooks', 'features/dark-mode'],
    },
    {
      type: 'category',
      label: 'Configuration',
      items: ['configuration', 'configuration/google-oauth', 'configuration/storage'],
    },
    'api',
    {
      type: 'category',
      label: 'Deployment',
      items: ['deployment/docker', 'deployment/cli'],
    },
    'contributing',
    'faq',
  ],
};

module.exports = sidebars;
