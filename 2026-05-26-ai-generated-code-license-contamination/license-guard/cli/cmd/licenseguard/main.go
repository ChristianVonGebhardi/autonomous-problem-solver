package main

import (
	"os"

	"github.com/licenseguard/cli/internal/commands"
)

func main() {
	if err := commands.Execute(); err != nil {
		os.Exit(1)
	}
}