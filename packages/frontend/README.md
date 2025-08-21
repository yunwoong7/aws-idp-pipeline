<h2 align="center">AWS IDP Frontend</h2>

<div align="center">
  <img src="https://img.shields.io/badge/Next.js-15.3-000000?logo=nextdotjs&logoColor=white"/>
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white"/>
  <img src="https://img.shields.io/badge/TypeScript-5.x-3178C6?logo=typescript&logoColor=white"/>
  <img src="https://img.shields.io/badge/Tailwind-CSS-06B6D4?logo=tailwindcss&logoColor=white"/>
</div>

---

## Overview

This package contains the Next.js frontend for the AWS IDP application. It provides the user interface for document management, analysis, and interaction with the AI agent.

## Core Pages & Features

- **Landing Page (`/`)**: The initial entry point of the application.
- **Studio Page (`/studio`)**: The main home page where users can select an index and begin the document analysis process.
- **Indexes Page (`/indexes`)**: Allows users to create, view, and manage their data indexes.
- **Workspace Page (`/workspace`)**: The core analysis environment where users can view document processing results and interact with the AI.
- **Settings Page (`/settings`)**: Provides options to configure MCP tools and customize application branding, such as the logo and title.

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **Language**: TypeScript
- **UI**: React 19, Tailwind CSS, Radix UI, Shadcn UI
- **State Management**: React Context, Zustand
- **Animations**: Framer Motion
- **Icons**: Lucide React

## Project Structure

The `src/app` directory contains the primary pages:

```
src/app/
├── page.tsx          # Landing Page
├── studio/           # Main home/dashboard page
├── indexes/          # Index management page
├── workspace/        # Core analysis workspace
├── settings/         # Application and tool settings
└── ...               # Other pages and API routes
```

## Getting Started

To set up and run this frontend, please follow the comprehensive guides in the root of the repository:

- **For a containerized setup (Recommended):** See [**Devcontainer Setup Guide**](../../docs/devcontainer_setup.md)
- **For a manual local setup:** See [**Manual Local Setup Guide**](../../docs/manual_setup.md)

The setup process includes installing all dependencies and configuring the necessary environment variables.

## Available Scripts

Once the environment is set up, you can use the following scripts from the **project root**:

- `pnpm dev`: Starts the frontend development server.
- `pnpm build`: Creates a production build of the frontend.
- `pnpm start`: Starts the production server.
- `pnpm lint`: Lints the codebase using ESLint.
- `pnpm type-check`: Runs the TypeScript compiler to check for type errors.
