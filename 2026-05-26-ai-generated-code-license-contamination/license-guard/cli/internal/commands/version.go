package commands

import (
	"fmt"

	"github.com/spf13/cobra"
)

var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print the version of LicenseGuard CLI",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("LicenseGuard CLI v1.0.0")
		fmt.Println("License contamination detection for AI-generated code")
	},
}