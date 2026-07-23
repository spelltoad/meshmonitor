FROM golang:alpine AS builder

WORKDIR /build

COPY go.mod go.sum ./
RUN go mod download 

COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o collector main.go

FROM alpine

WORKDIR /app

RUN apk --no-cache add ca-certificates tzdata

COPY --from=builder /build/collector .

EXPOSE 8080

CMD ["./collector"]

