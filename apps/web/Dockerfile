FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY app ./app
COPY components ./components
COPY lib ./lib
COPY next.config.mjs ./
COPY tsconfig.json ./
COPY next-env.d.ts ./

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
