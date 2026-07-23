package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	_ "github.com/lib/pq"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"log"
	"net/http"
	"os"
)

type TelemetryData struct {
	SourceMachine    string  `json:"source_machine"`
	DestinsationNode string  `json:"destination_node"`
	LayerTested      string  `json:"layer_tested"`
	LatencyMs        float64 `json:"latency_ms"`
	IsUp             bool    `json:"is_up"`
	ErrorMessage     string  `json:"error_message"`
}

var db *sql.DB

var networkLatencyGauge = prometheus.NewGaugeVec(
	prometheus.GaugeOpts{
		Name: "network_latency_seconds",
		Help: "current latency between nodes in seconds",
	},
	[]string{"from", "to", "layer"},
)

func init() {
	prometheus.MustRegister(networkLatencyGauge)
}

func main() {
	dbHost := os.Getenv("DB_HOST")
	dbUser := os.Getenv("DB_USER")
	dbPassword := os.Getenv("DB_PASSWORD")
	dbName := os.Getenv("DB_NAME")
	connStr := fmt.Sprintf("host=%s port=5432 user=%s password=%s dbname=%s sslmode=disable", dbHost, dbUser, dbPassword, dbName)
	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatalf("Error connecting to db: %v", err)
	}
	defer db.Close()
	http.HandleFunc("/api/v1/telemetry", telemetryHandler)
	http.Handle("/metrics", promhttp.Handler())
	fmt.Println("Launched on :8080")
	log.Fatal(http.ListenAndServe(":8080", nil))
}

func telemetryHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST is allowed", http.StatusMethodNotAllowed)
		return
	}
	var data TelemetryData
	err := json.NewDecoder(r.Body).Decode(&data)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	networkLatencyGauge.WithLabelValues(data.SourceMachine, data.DestinsationNode, data.LayerTested).Set(data.LatencyMs / 1000.0)
	go func(d TelemetryData) {
		query := `INSERT INTO network_logs (source_machine, destination_node, layer_tested, latency_ms, is_up, error_message)
		VALUES ($1, $2, $3, $4, $5, $6)`
		_, err := db.Exec(query, d.SourceMachine, d.DestinsationNode, d.LayerTested, d.LatencyMs, d.IsUp, d.ErrorMessage)
		if err != nil {
			log.Printf("Error writing to db: %v", err)
		}
	}(data)
	w.WriteHeader(http.StatusAccepted)
	w.Write([]byte(`{"status":"delivered"}`))
}
