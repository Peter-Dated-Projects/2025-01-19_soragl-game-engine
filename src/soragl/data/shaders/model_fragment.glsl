#version 330 core

in vec3 f_position;
in vec3 f_normal;
in vec2 f_uv;

out vec4 color;

uniform sampler2D[10] u_textures;


void main() {
    
    vec3 lightDir = normalize(vec3(0.0, 1.0, 0.0));
    float diff = max(dot(f_normal, lightDir), 0.0);
    vec3 diffuse = diff * vec3(1.0, 1.0, 1.0);

    color = texture(u_textures[0], f_uv);// * vec4(diffuse, 1.0);
}