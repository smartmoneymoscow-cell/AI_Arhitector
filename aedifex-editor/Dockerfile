FROM node:20-slim

WORKDIR /app

# Install bun
RUN npm install -g bun

# Copy package files
COPY package.json bun.lock ./
COPY packages/core/package.json ./packages/core/
COPY packages/viewer/package.json ./packages/viewer/
COPY packages/editor/package.json ./packages/editor/
COPY packages/ui/package.json ./packages/ui/
COPY packages/mcp/package.json ./packages/mcp/
COPY packages/ifc-converter/package.json ./packages/ifc-converter/
COPY apps/editor/package.json ./apps/editor/
COPY tooling/ ./tooling/

# Install dependencies
RUN bun install --frozen-lockfile 2>/dev/null || bun install

# Copy source
COPY . .

# Build
RUN bun build 2>/dev/null || true

EXPOSE 3002

CMD ["bun", "dev", "--host", "0.0.0.0", "--port", "3002"]
