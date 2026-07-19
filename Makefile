CC=gcc
CFLAGS=-c -std=gnu99 -W -Wall -Wextra -pedantic -MMD -MP -g3 -Og -Iinclude
CXX=g++
CXXFLAGS=-c -std=gnu++11 -W -Wall -Wextra -pedantic -MMD -MP -g3 -Og -Iinclude
LD=gcc
LDFLAGS=
SOURCES_C=$(shell find src -name '*.c')
SOURCES_CPP=$(shell find src -name '*.cpp')
OBJECTS_C=$(SOURCES_C:src/%.c=obj/%.c.o)
OBJECTS_CPP=$(SOURCES_CPP:src/%.cpp=obj/%.cpp.o)
OBJECTS=$(OBJECTS_C) $(OBJECTS_CPP)
DEPENDENCIES_C=$(OBJECTS_C:obj/%.c.o=obj/%.c.d)
DEPENDENCIES_CPP=$(OBJECTS_CPP:obj/%.cpp.o=obj/%.cpp.d)
DEPENDENCIES=$(DEPENDENCIES_C) $(DEPENDENCIES_CPP)
MKDIR=mkdir -p
RM=rm -rf

ifeq ($(OS),Windows_NT)
	EXECUTABLE=bin/softmodem.exe
else
	EXECUTABLE=bin/softmodem
endif

all: $(EXECUTABLE)

$(EXECUTABLE): $(OBJECTS)
	if [ ! -d $(dir $@) ]; then \
		$(MKDIR) $(dir $@); \
	fi

	$(LD) $^ $(LDFLAGS) -o $@

obj/%.cpp.o: src/%.cpp
	if [ ! -d $(dir $@) ]; then \
		$(MKDIR) $(dir $@); \
	fi

	$(CXX) $(CXXFLAGS) $< -o $@

obj/%.c.o: src/%.c
	if [ ! -d $(dir $@) ]; then \
		$(MKDIR) $(dir $@); \
	fi

	$(CC) $(CFLAGS) $< -o $@

clean:
	$(RM) obj bin

.PHONY: all clean

-include $(DEPENDENCIES)
