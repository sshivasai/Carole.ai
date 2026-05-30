FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy application code
COPY . .

# Expose Next.js default port
EXPOSE 3000

# Run in development mode for hot-reloading
CMD ["npm", "run", "dev"]
