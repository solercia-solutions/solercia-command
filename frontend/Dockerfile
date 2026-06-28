FROM node:22-alpine

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY package*.json ./
RUN npm install

# Copy the rest of the application source.
COPY . .

EXPOSE 4200

# ng serve binds to 0.0.0.0:4200 with polling for container file watching.
CMD ["npm", "start"]
