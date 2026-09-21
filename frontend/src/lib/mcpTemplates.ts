/**
 * Pre-configured MCP & Integration Templates for Carole.ai.
 * Provides 1-click connect templates with predefined commands, args, and credential fields.
 */

export interface McpField {
  key: string;
  label: string;
  placeholder: string;
  required?: boolean;
  isSecret?: boolean;
  type?: "text" | "password" | "textarea";
  helpText?: string;
  defaultValue?: string;
}

export interface McpTemplate {
  id: string;
  name: string;
  category: "Developer" | "Database" | "Productivity" | "Communication" | "Finance & CRM" | "Cloud & Search";
  description: string;
  command: string;
  args: string;
  docsUrl: string;
  badge?: string;
  fields: McpField[];
  logo: string; // Key matching IntegrationLogos component
}

export const MCP_TEMPLATES: McpTemplate[] = [
  // ── Developer Tools ────────────────────────────────────────────────────────
  {
    id: "github",
    name: "GitHub",
    category: "Developer",
    description: "Inspect repositories, file issues, review PRs, search code, and manage workflows.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-github",
    docsUrl: "https://github.com/settings/tokens",
    badge: "Official",
    logo: "github",
    fields: [
      {
        key: "GITHUB_PERSONAL_ACCESS_TOKEN",
        label: "Personal Access Token",
        placeholder: "ghp_xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Needs 'repo', 'workflow', and 'read:org' scopes.",
      },
    ],
  },
  {
    id: "gitlab",
    name: "GitLab",
    category: "Developer",
    description: "Interact with GitLab projects, merge requests, issues, pipelines, and wiki.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-gitlab",
    docsUrl: "https://gitlab.com/-/user_settings/personal_access_tokens",
    badge: "Popular",
    logo: "gitlab",
    fields: [
      {
        key: "GITLAB_PERSONAL_ACCESS_TOKEN",
        label: "Personal Access Token",
        placeholder: "glpat-xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Create a token with 'api' and 'read_repository' scopes.",
      },
      {
        key: "GITLAB_API_URL",
        label: "GitLab Instance URL (Optional)",
        placeholder: "https://gitlab.com/api/v4",
        required: false,
        defaultValue: "https://gitlab.com/api/v4",
      },
    ],
  },
  {
    id: "sentry",
    name: "Sentry",
    category: "Developer",
    description: "Search production error issues, view stack traces, and analyze crash telemetry.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-sentry",
    docsUrl: "https://sentry.io/settings/account/api/auth-tokens/",
    logo: "sentry",
    fields: [
      {
        key: "SENTRY_AUTH_TOKEN",
        label: "Auth Token",
        placeholder: "sntrys_xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "User auth token from Sentry settings.",
      },
    ],
  },
  {
    id: "puppeteer",
    name: "Puppeteer Web Automator",
    category: "Developer",
    description: "Direct Headless Chromium execution for automated scraping and testing.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-puppeteer",
    docsUrl: "https://pptr.dev",
    logo: "puppeteer",
    fields: [
      {
        key: "DOCKER_CONTAINER",
        label: "Headless Sandbox Options (Optional)",
        placeholder: "allow-all",
        required: false,
      },
    ],
  },
  {
    id: "docker",
    name: "Docker",
    category: "Developer",
    description: "Manage local & remote Docker containers, images, volumes, and compose swarms.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-docker",
    docsUrl: "https://docs.docker.com",
    badge: "Popular",
    logo: "docker",
    fields: [
      {
        key: "DOCKER_HOST",
        label: "Docker Host (Optional)",
        placeholder: "unix:///var/run/docker.sock",
        required: false,
      },
    ],
  },

  // ── Databases ──────────────────────────────────────────────────────────────
  {
    id: "mongodb",
    name: "MongoDB",
    category: "Database",
    description: "Query documents, aggregate collections, inspect BSON schemas, and run analytics.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-mongodb",
    docsUrl: "https://www.mongodb.com/docs/atlas/",
    badge: "Official",
    logo: "mongodb",
    fields: [
      {
        key: "MONGODB_URI",
        label: "MongoDB Connection URI",
        placeholder: "mongodb+srv://user:pass@cluster.mongodb.net/dbname",
        required: true,
        isSecret: true,
        helpText: "Atlas or self-hosted MongoDB connection string.",
      },
    ],
  },
  {
    id: "postgres",
    name: "PostgreSQL",
    category: "Database",
    description: "Run schema introspection, execute read queries, and analyze table structures.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-postgres",
    docsUrl: "https://www.postgresql.org/docs/",
    badge: "Official",
    logo: "postgres",
    fields: [
      {
        key: "POSTGRES_URL",
        label: "Database Connection URI",
        placeholder: "postgresql://user:password@localhost:5432/mydb",
        required: true,
        isSecret: true,
        helpText: "Connection string with read/write access.",
      },
    ],
  },
  {
    id: "redis",
    name: "Redis",
    category: "Database",
    description: "Query Redis keys, streams, cached objects, and pub/sub message queues.",
    command: "uvx",
    args: "mcp-server-redis",
    docsUrl: "https://redis.io/docs/",
    logo: "redis",
    fields: [
      {
        key: "REDIS_URL",
        label: "Redis Connection URL",
        placeholder: "redis://localhost:6379",
        required: true,
        defaultValue: "redis://localhost:6379",
      },
    ],
  },
  {
    id: "supabase",
    name: "Supabase",
    category: "Database",
    description: "Manage Supabase tables, Postgres functions, Auth users, and Storage buckets.",
    command: "npx",
    args: "-y,@supabase/mcp-server",
    docsUrl: "https://supabase.com/dashboard/project/_/settings/api",
    badge: "Popular",
    logo: "supabase",
    fields: [
      {
        key: "SUPABASE_URL",
        label: "Project URL",
        placeholder: "https://xyzcompany.supabase.co",
        required: true,
      },
      {
        key: "SUPABASE_SERVICE_ROLE_KEY",
        label: "Service Role Key (Secret)",
        placeholder: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        required: true,
        isSecret: true,
      },
    ],
  },

  // ── Communication ──────────────────────────────────────────────────────────
  {
    id: "slack",
    name: "Slack",
    category: "Communication",
    description: "Post messages, query channels, retrieve message threads, and reply to team members.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-slack",
    docsUrl: "https://api.slack.com/apps",
    badge: "Official",
    logo: "slack",
    fields: [
      {
        key: "SLACK_BOT_TOKEN",
        label: "Bot User OAuth Token",
        placeholder: "xoxb-xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Starts with 'xoxb-'. Needs channels:read, chat:write scopes.",
      },
      {
        key: "SLACK_TEAM_ID",
        label: "Slack Team / Workspace ID",
        placeholder: "T0123456789",
        required: true,
      },
    ],
  },
  {
    id: "discord",
    name: "Discord",
    category: "Communication",
    description: "Send channel notifications, inspect Discord servers, and interact with guilds.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-discord",
    docsUrl: "https://discord.com/developers/applications",
    logo: "discord",
    fields: [
      {
        key: "DISCORD_BOT_TOKEN",
        label: "Discord Bot Token",
        placeholder: "MTE0xxxxxxxxxxxxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },

  // ── Productivity & Project Management ──────────────────────────────────────
  {
    id: "linear",
    name: "Linear",
    category: "Productivity",
    description: "Create and update issues, query sprint cycles, and track bug tickets.",
    command: "npx",
    args: "-y,@linear/mcp-server",
    docsUrl: "https://linear.app/settings/api",
    badge: "Popular",
    logo: "linear",
    fields: [
      {
        key: "LINEAR_API_KEY",
        label: "Linear API Key",
        placeholder: "lin_api_xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Generate a personal API key from Linear Settings → API.",
      },
    ],
  },
  {
    id: "notion",
    name: "Notion",
    category: "Productivity",
    description: "Read & write Notion pages, query databases, and append structured documentation.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-notion",
    docsUrl: "https://www.notion.so/my-integrations",
    badge: "Official",
    logo: "notion",
    fields: [
      {
        key: "NOTION_API_KEY",
        label: "Internal Integration Secret",
        placeholder: "secret_xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Create an integration and connect it to your workspace pages.",
      },
    ],
  },
  {
    id: "jira",
    name: "Jira & Confluence",
    category: "Productivity",
    description: "Manage Atlassian Jira epics/tasks, sprints, and Confluence wiki spaces.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-atlassian",
    docsUrl: "https://id.atlassian.com/manage-profile/security/api-tokens",
    logo: "jira",
    fields: [
      {
        key: "CONFLUENCE_DOMAIN",
        label: "Atlassian Subdomain (e.g. yourorg.atlassian.net)",
        placeholder: "yourcompany.atlassian.net",
        required: true,
      },
      {
        key: "ATLASSIAN_EMAIL",
        label: "Account Email",
        placeholder: "developer@company.com",
        required: true,
      },
      {
        key: "ATLASSIAN_API_TOKEN",
        label: "API Token",
        placeholder: "ATATT3xFfGF0xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },
  {
    id: "google-drive",
    name: "Google Drive & Docs",
    category: "Productivity",
    description: "Search Google Drive files, extract text from Docs/Sheets, and export assets.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-google-drive",
    docsUrl: "https://console.cloud.google.com/apis/credentials",
    logo: "google-drive",
    fields: [
      {
        key: "GOOGLE_DRIVE_CREDENTIALS",
        label: "Service Account / OAuth Credentials JSON",
        placeholder: '{"type": "service_account", "project_id": "..."}',
        required: true,
        type: "textarea",
        isSecret: true,
      },
    ],
  },
  {
    id: "airtable",
    name: "Airtable",
    category: "Productivity",
    description: "Query and update Airtable bases, records, linked tables, and views.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-airtable",
    docsUrl: "https://airtable.com/create/tokens",
    logo: "airtable",
    fields: [
      {
        key: "AIRTABLE_API_KEY",
        label: "Personal Access Token",
        placeholder: "patxxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },
  {
    id: "figma",
    name: "Figma",
    category: "Productivity",
    description: "Inspect Figma design frames, extract component CSS/properties, and download vector assets.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-figma",
    docsUrl: "https://www.figma.com/developers/api#access-tokens",
    logo: "figma",
    fields: [
      {
        key: "FIGMA_ACCESS_TOKEN",
        label: "Personal Access Token",
        placeholder: "figd_xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },
  {
    id: "asana",
    name: "Asana",
    category: "Productivity",
    description: "Manage Asana projects, assign tasks to teammates, and query workspace milestones.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-asana",
    docsUrl: "https://app.asana.com/0/my-apps",
    logo: "asana",
    fields: [
      {
        key: "ASANA_ACCESS_TOKEN",
        label: "Personal Access Token",
        placeholder: "1/120xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },

  // ── Finance & CRM ──────────────────────────────────────────────────────────
  {
    id: "stripe",
    name: "Stripe",
    category: "Finance & CRM",
    description: "Query charges, invoices, subscription tiers, customer records, and payment events.",
    command: "npx",
    args: "-y,@stripe/mcp-server",
    docsUrl: "https://dashboard.stripe.com/apikeys",
    badge: "Official",
    logo: "stripe",
    fields: [
      {
        key: "STRIPE_SECRET_KEY",
        label: "Secret Key (Test or Live)",
        placeholder: "sk_test_51xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Restricted or standard secret key from Stripe dashboard.",
      },
    ],
  },
  {
    id: "hubspot",
    name: "HubSpot",
    category: "Finance & CRM",
    description: "Search CRM contacts, deals, company pipelines, and customer notes.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-hubspot",
    docsUrl: "https://app.hubspot.com/private-apps",
    logo: "hubspot",
    fields: [
      {
        key: "HUBSPOT_ACCESS_TOKEN",
        label: "Private App Access Token",
        placeholder: "pat-na1-xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },

  // ── Cloud & Search ─────────────────────────────────────────────────────────
  {
    id: "aws-s3",
    name: "AWS Cloud & S3",
    category: "Cloud & Search",
    description: "Read, write, and list objects across Amazon S3 buckets and AWS cloud assets.",
    command: "uvx",
    args: "mcp-server-aws-s3",
    docsUrl: "https://aws.amazon.com/console/",
    logo: "aws",
    fields: [
      {
        key: "AWS_ACCESS_KEY_ID",
        label: "Access Key ID",
        placeholder: "AKIAIOSFODNN7EXAMPLE",
        required: true,
      },
      {
        key: "AWS_SECRET_ACCESS_KEY",
        label: "Secret Access Key",
        placeholder: "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        required: true,
        isSecret: true,
      },
      {
        key: "AWS_REGION",
        label: "AWS Region",
        placeholder: "us-east-1",
        defaultValue: "us-east-1",
        required: true,
      },
    ],
  },
  {
    id: "brave-search",
    name: "Brave Web Search",
    category: "Cloud & Search",
    description: "Independent web search index with fast text snippets, news, and links.",
    command: "npx",
    args: "-y,@modelcontextprotocol/server-brave-search",
    docsUrl: "https://brave.com/search/api/",
    badge: "Official",
    logo: "brave-search",
    fields: [
      {
        key: "BRAVE_API_KEY",
        label: "Brave Search API Key",
        placeholder: "BSAxxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
      },
    ],
  },
  {
    id: "perplexity",
    name: "Perplexity AI Search",
    category: "Cloud & Search",
    description: "Real-time AI grounded web search, citation retrieval, and factual research engine.",
    command: "npx",
    args: "-y,perplexity-mcp",
    docsUrl: "https://www.perplexity.ai/settings/api",
    badge: "Popular",
    logo: "perplexity",
    fields: [
      {
        key: "PERPLEXITY_API_KEY",
        label: "Perplexity API Key",
        placeholder: "pplx-xxxxxxxxxxxxxxxxxxxx",
        required: true,
        isSecret: true,
        helpText: "Obtain an API key from Perplexity AI account settings.",
      },
    ],
  },
];
