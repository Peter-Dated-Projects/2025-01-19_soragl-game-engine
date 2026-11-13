#version 330 core

layout (location = 0) in vec2 in_position;

out vec2 f_uv;

void main() {
    // GL-rendered textures are already bottom-up, unlike pygame surfaces
    f_uv = in_position * 0.5 + 0.5;
    gl_Position = vec4(in_position, 0.0, 1.0);
}
