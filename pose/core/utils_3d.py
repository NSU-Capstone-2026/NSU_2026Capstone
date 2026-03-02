# utils_3d.py
import cv2
import numpy as np

def get_projection_matrix(mtx, rvec, tvec):
    """
    카메라 내부 파라미터(mtx)와 외부 파라미터(rvec, tvec)를 결합하여
    3x4 Projection Matrix (P)를 만듭니다.
    P = K * [R | t]
    """
    R, _ = cv2.Rodrigues(rvec) # 3x3 회전 행렬로 변환
    
    # [수정됨] tvec가 (3,) 형태의 1차원 배열일 경우 (3,1) 2차원으로 변환
    # 이 부분이 없으면 np.hstack에서 ValueError가 발생합니다.
    t = np.array(tvec).reshape(3, 1)
    
    # [R | t] 합치기 (3x4 행렬)
    Rt = np.hstack((R, t))
    
    # Projection Matrix 계산 P = K * [R|t]
    P = mtx @ Rt
    return P

def triangulate_points(proj_matrices, points_2d):
    """
    여러 카메라의 Projection Matrix(P)와 2D 좌표를 받아 3D 좌표를 계산합니다.
    (최소 2개 이상의 카메라 데이터 필요)
    """
    n_views = len(proj_matrices)
    if n_views < 2:
        return None

    points_2d = np.asarray(points_2d)
    if points_2d.shape[0] != 2 or points_2d.shape[1] != n_views:
        raise ValueError("points_2d must have shape (2, N_views)")

    # 다중 시점 DLT: 각 카메라에서 2개의 식을 쌓아 AX=0을 SVD로 풉니다.
    A = []
    for i in range(n_views):
        P = proj_matrices[i]
        x, y = points_2d[0, i], points_2d[1, i]
        A.append(x * P[2] - P[0])
        A.append(y * P[2] - P[1])

    _, _, vt = np.linalg.svd(np.asarray(A))
    X = vt[-1]

    if np.isclose(X[3], 0.0):
        return None

    points_3d = X[:3] / X[3]
    return points_3d.flatten() # [x, y, z] 반환

def calculate_angle_3d(a, b, c):
    """
    3개의 3D 점(A, B, C)이 주어졌을 때, 점 B(중심)에서의 각도를 계산합니다.
    """
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)

    # 벡터 BA (팔꿈치 -> 어깨)
    ba = a - b
    # 벡터 BC (팔꿈치 -> 손목)
    bc = c - b

    # 벡터의 내적(Dot Product)과 크기(Norm)를 이용한 각도 계산
    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)

    if norm_ba == 0 or norm_bc == 0:
        return 0.0

    cosine_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    
    # 수학적 오차로 인해 -1~1 범위를 벗어나는 것 방지
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

    return np.degrees(angle)
