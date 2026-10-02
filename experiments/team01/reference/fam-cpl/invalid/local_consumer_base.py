import consumer


def main():
    assert consumer.from_base(2000, "m", {"mm": 1, "cm": 10, "m": 1000}) == 2.0
    assert consumer.from_base(500, "cm", {"mm": 1, "cm": 10, "m": 1000}) == 50.0
    print("local-consumer-base-green")


if __name__ == "__main__":
    main()
