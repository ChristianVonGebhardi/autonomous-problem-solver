package commands

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var cfgFile string

var rootCmd = &cobra.Command{
	Use:   "licenseguard",
	Short: "LicenseGuard - AI-Generated Code License Contamination Detector",
	Long: `LicenseGuard scans code for potential open-source license contamination
from AI-generated code. It analyzes code using MinHash fingerprinting and
semantic similarity to detect copied FOSS code.`,
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	cobra.OnInitialize(initConfig)

	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default: $HOME/.licenseguard.yaml)")
	rootCmd.PersistentFlags().String("api-url", "http://localhost:8000", "LicenseGuard API URL")
	rootCmd.PersistentFlags().String("api-key", "", "API authentication key")
	rootCmd.PersistentFlags().Bool("verbose", false, "Enable verbose output")

	viper.BindPFlag("api_url", rootCmd.PersistentFlags().Lookup("api-url"))
	viper.BindPFlag("api_key", rootCmd.PersistentFlags().Lookup("api-key"))
	viper.BindPFlag("verbose", rootCmd.PersistentFlags().Lookup("verbose"))

	rootCmd.AddCommand(scanCmd)
	rootCmd.AddCommand(installHookCmd)
	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(versionCmd)
}

func initConfig() {
	if cfgFile != "" {
		viper.SetConfigFile(cfgFile)
	} else {
		home, err := os.UserHomeDir()
		if err == nil {
			viper.AddConfigPath(home)
		}
		viper.AddConfigPath(".")
		viper.SetConfigName(".licenseguard")
		viper.SetConfigType("yaml")
	}

	viper.SetEnvPrefix("LICENSEGUARD")
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err == nil {
		if viper.GetBool("verbose") {
			fmt.Fprintln(os.Stderr, "Using config file:", viper.ConfigFileUsed())
		}
	}
}