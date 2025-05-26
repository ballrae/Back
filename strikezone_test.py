import matplotlib.pyplot as plt
import numpy as np

# 예시 데이터 : 250522 HHvsNC 2회말 8번타자 박세혁 타석
data = [{"pitchId":"250522_190439","inn":2,"ballcount":1,"crossPlateX":0.456147,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-135.073,"vz0":-9.6567,"vx0":8.94903,"z0":6.04566,"y0":50.0,"x0":-2.19054,"ax":-10.9058,"ay":39.8427,"az":-10.3562,"stance":"L"},{"pitchId":"250522_190805","inn":2,"ballcount":2,"crossPlateX":-1.38572,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-121.389,"vz0":-0.783804,"vx0":3.08395,"z0":6.33268,"y0":50.0,"x0":-2.6206,"ax":-1.0333,"ay":33.3236,"az":-37.8444,"stance":"L"},{"pitchId":"250522_190826","inn":2,"ballcount":3,"crossPlateX":-0.548075,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-124.892,"vz0":-5.90615,"vx0":7.09015,"z0":6.18715,"y0":50.0,"x0":-2.59601,"ax":-10.5555,"ay":36.359,"az":-32.9795,"stance":"L"},{"pitchId":"250522_190908","inn":2,"ballcount":4,"crossPlateX":-0.768297,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-125.645,"vz0":-3.1178,"vx0":6.41412,"z0":6.22301,"y0":50.0,"x0":-2.45481,"ax":-11.3586,"ay":35.2147,"az":-28.1468,"stance":"L"},{"pitchId":"250522_191001","inn":2,"ballcount":5,"crossPlateX":-0.088105,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-136.983,"vz0":-2.85941,"vx0":8.11684,"z0":6.23778,"y0":50.0,"x0":-2.17635,"ax":-13.9288,"ay":43.9051,"az":-16.9663,"stance":"L"},{"pitchId":"250522_191022","inn":2,"ballcount":6,"crossPlateX":-0.911509,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-125.525,"vz0":-1.63452,"vx0":5.68046,"z0":6.36649,"y0":50.0,"x0":-2.46305,"ax":-9.3905,"ay":34.556,"az":-27.6769,"stance":"L"},{"pitchId":"250522_191046","inn":2,"ballcount":7,"crossPlateX":0.527834,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-125.544,"vz0":-2.43513,"vx0":8.17932,"z0":6.21974,"y0":50.0,"x0":-2.22097,"ax":-7.59194,"ay":34.7161,"az":-36.3262,"stance":"L"},{"pitchId":"250522_191115","inn":2,"ballcount":8,"crossPlateX":0.677905,"crossPlateY":0.7083,"topSz":3.305,"bottomSz":1.603,"vy0":-137.441,"vz0":-9.52307,"vx0":10.6349,"z0":6.00638,"y0":50.0,"x0":-2.39193,"ax":-13.508,"ay":41.8481,"az":-5.77682,"stance":"L"}]

# y = 0 (홈플레이트)에 도달하는 시간 t 계산
def compute_plate_coordinates(pitch):
    y0, vy0, ay = pitch["y0"], pitch["vy0"], pitch["ay"]
    a = 0.5 * ay
    b = vy0
    c = y0
    t = (-b - np.sqrt(b**2 - 4*a*c)) / (2*a)
    x = pitch["x0"] + pitch["vx0"] * t + 0.5 * pitch["ax"] * t**2
    z = pitch["z0"] + pitch["vz0"] * t + 0.5 * pitch["az"] * t**2
    return x, z

# 계산된 좌표
points = [compute_plate_coordinates(pitch) for pitch in data]

# 스트라이크존 기준
strike_zone_left = -0.75
strike_zone_right = 0.75
strike_zone_top = data[0]['topSz']
strike_zone_bottom = data[0]['bottomSz']
zone_width = (strike_zone_right - strike_zone_left) / 3
zone_height = (strike_zone_top - strike_zone_bottom) / 3

# 시각화
fig, ax = plt.subplots(figsize=(6, 6))

# 스트라이크존 외곽
ax.plot([strike_zone_left, strike_zone_right, strike_zone_right, strike_zone_left, strike_zone_left],
        [strike_zone_bottom, strike_zone_bottom, strike_zone_top, strike_zone_top, strike_zone_bottom],
        color="black", linewidth=2)

# 내부 3x3 구획
for i in range(1, 3):
    ax.axvline(strike_zone_left + i * zone_width, color='gray', linestyle='--', linewidth=1)
    ax.axhline(strike_zone_bottom + i * zone_height, color='gray', linestyle='--', linewidth=1)

result = ['foul', 'ball', 'swing', 'foul', 'ball', 'ball', 'foul', 'hit']

# 점 찍기
for i, (x, z) in enumerate(points):
    color="orange"
    if result[i]=="ball": color="limegreen"
    elif result[i]=="hit": color="royalblue"

    ax.scatter(x, z, s=200, color=color, edgecolors='white', linewidth=1.5, zorder=3)
    ax.text(x, z, str(i+1), color='black', ha='center', va='center', fontsize=10, weight='bold')

# 설정
ax.set_xlim(-2, 2)
ax.set_ylim(0, 4.5)
ax.set_aspect('equal')
ax.set_title("pitch sequence from data", fontsize=14)
ax.axis("off")

plt.tight_layout()
plt.show()