from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parent
def run(args):
    print("\n>>>", " ".join(args), flush=True)
    subprocess.run(args,cwd=ROOT,check=True)
if __name__=="__main__":
    py=sys.executable
    (ROOT/"state").mkdir(parents=True,exist_ok=True)
    (ROOT/"outputs").mkdir(parents=True,exist_ok=True)
    run([py,"generate_data.py"])
    run([py,"-m","src.part_a"])
    run([py,"-m","src.part_b"])
    run([py,"-m","src.part_c"])
    run([py,"-m","src.part_d"])
    print("\nPipeline finished. Review outputs/ and README.md.")
