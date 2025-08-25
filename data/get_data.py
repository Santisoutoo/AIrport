"""
Class for downloading complete airport .dat files from X-Plane Scenery Gateway.
"""

from pathlib import Path
from typing import Optional
from xplane_airports.gateway import scenery_pack
from requests import HTTPError


class XPlaneAirportDownloader:
    """
    Downloader for airport .dat files from X-Plane Scenery Gateway.
    """
    def __init__(
        self,
        icao_code: str,
        output_directory: str | Path = None
    ):

        self.icao_code = icao_code.strip().upper()
        
        if output_directory is None:
            # Default: airport_data relative to this module
            self.base_output_dir = Path(__file__).parent / "airport_data"
        else:
            output_path = Path(output_directory)
            if output_path.is_absolute():
                self.base_output_dir = output_path
            else:
                self.base_output_dir = Path(__file__).parent / output_path
        
        # Create specific folder for each airport: base_dir/ICAO_CODE/
        self.output_dir = self.base_output_dir / self.icao_code
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def download(self, retries: int = 3, verbose: bool = True, skip_if_exists: bool = True) -> Optional[Path]:
        """
        Downloads the complete .dat file of the configured airport.
        
        Args:
            retries: Number of retries in case of error
            verbose: If True, shows download progress and completion info
            skip_if_exists: If True, skips download if file already exists
            
        Returns:
            Path to the downloaded file or None if error
        """
        # Check if file already exists
        output_file = self.output_dir / f"{self.icao_code}.dat"
        
        if skip_if_exists and output_file.exists():
            if verbose:
                size_mb = output_file.stat().st_size / 1024 / 1024
                print(f"✅ {self.icao_code} already exists ({size_mb:.2f} MB) in: {output_file.parent}")
            return output_file
        
        try:
            if verbose:
                print(f"📥 Downloading {self.icao_code}...")
            
            # Download the recommended scenery package
            pack = scenery_pack(self.icao_code, retries_on_error=retries)
            
            if pack is None or pack.apt is None:
                if verbose:
                    print(f"❌ No data found for airport {self.icao_code}")
                return None
            
            # Save the complete .dat file without modifications
            with open(output_file, 'w', encoding='utf-8') as f:
                # Write all airport lines as they come
                for line in pack.apt.text:
                    # If line is an AptDatLine object, get the text
                    if hasattr(line, 'raw_line'):
                        f.write(line.raw_line + '\n')
                    elif hasattr(line, '__str__'):
                        f.write(str(line) + '\n')
                    else:
                        f.write(line + '\n')
            
            if verbose:
                size_mb = output_file.stat().st_size / 1024 / 1024
                print(f"✅ {self.icao_code} download completed ({size_mb:.2f} MB) - Saved in: {output_file.parent}")
            
            return output_file
            
        except HTTPError as e:
            if e.response and e.response.status_code == 404:
                if verbose:
                    print(f"❌ Airport {self.icao_code} not found")
            else:
                if verbose:
                    print(f"❌ HTTP error: {e}")
        except Exception as e:
            if verbose:
                print(f"❌ Error downloading {self.icao_code}: {e}")
            
        return None
    
    def exists(self) -> bool:
        """
        Checks if the .dat file for this airport already exists.
        
        Returns:
            True if the file exists, False otherwise
        """
        dat_file = self.output_dir / f"{self.icao_code}.dat"
        return dat_file.exists()
    
    def get_file_path(self) -> Path:
        """
        Returns the complete path where the .dat file will be saved.
        
        Returns:
            Path of the .dat file
        """
        return self.output_dir / f"{self.icao_code}.dat"
    
    def get_directory(self) -> Path:
        """
        Returns the configured output directory.
        
        Returns:
            Path of the output directory
        """
        return self.output_dir


if __name__ == "__main__":
    # Simple test - download one airport with detailed info
    downloader = XPlaneAirportDownloader("LEMD")
    downloader.download()