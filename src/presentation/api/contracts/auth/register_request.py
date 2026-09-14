from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr = Field(
        ...,
        description="Địa chỉ email. Phải là email hợp lệ.",
    )

    password: str = Field(
        ...,
        min_length=6,
        description="Mật khẩu. Tối thiểu 6 ký tự.",
    )

    full_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Họ và tên đầy đủ.",
    )

    school_code: str = Field(
        default="",
        max_length=50,
        description=(
            "Mã trường. Giá trị hợp lệ: ADMIN, HUST, HUCE, STUDENT. "
            "Để trống = đăng ký tài khoản không thuộc trường cụ thể."
        ),
    )
