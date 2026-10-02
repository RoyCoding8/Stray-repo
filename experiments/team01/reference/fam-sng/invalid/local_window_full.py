import compute


def main():
    spec = {"op": "window_sum"}
    assert compute.compute(spec, {"nums": [3, 5, 7], "k": 3}) == {"total": 15}
    assert compute.compute(spec, {"nums": [3, 5, 7], "k": 0}) == {"total": 0}
    print("local-window-full-green")


if __name__ == "__main__":
    main()
